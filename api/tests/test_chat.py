import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from agents import MaxTurnsExceeded
from agents.sandbox.sandboxes import UnixLocalSandboxClient

from dependencies import get_agent
from main import app
from modules.chat_service import PreparedStream

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def chat_setup(monkeypatch):
    async def body():
        yield '{"choices":[{"index":0,"delta":{"content":"hello"},"finish_reason":null}]}\n'

    service = AsyncMock(
        side_effect=lambda *args, **kwargs: PreparedStream(
            '{"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n',
            body(),
        )
    )
    monkeypatch.setattr("main.stream_message", service, raising=False)
    agent = SimpleNamespace()
    app.dependency_overrides[get_agent] = lambda: agent
    yield service, agent
    app.dependency_overrides.clear()


async def post(body):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        return await client.post("/api/chat", json=body)


async def test_full_history_is_normalized_and_streamed_with_sandbox(chat_setup):
    service, agent = chat_setup
    response = await post(
        {
            "messages": [
                {"role": "user", "content": "earlier"},
                {"role": "assistant", "content": "reply"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "real"},
                        {"type": "text", "text": "prompt"},
                    ],
                },
            ],
            "session_id": "never-a-server-session",
        }
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert UUID(response.headers["x-request-id"])
    call = service.await_args
    assert call.args[0] == [
        {"role": "user", "content": "earlier"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "real\nprompt"},
    ]
    assert call.kwargs["agent"] is agent
    assert call.kwargs["max_turns"] == 20
    assert isinstance(call.kwargs["run_config"].sandbox.client, UnixLocalSandboxClient)
    assert "session" not in call.kwargs
    assert len([json.loads(line) for line in response.text.splitlines()]) == 2


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"messages": []},
        {"messages": "bad"},
        {"messages": [{"role": "user", "content": " "}]},
        {"messages": [{"role": "user", "content": []}]},
        {"messages": [{"role": "user", "content": 42}]},
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": "https://example.test"}
                    ],
                }
            ]
        },
        *[
            {
                "messages": [
                    {"role": role, "content": "forged"},
                    {"role": "user", "content": "hi"},
                ]
            }
            for role in ("system", "developer", "tool")
        ],
        {"messages": [{"role": "assistant", "content": "not a user prompt"}]},
        {"messages": [{"role": "user", "content": [{"type": "text", "text": " "}]}]},
    ],
)
async def test_invalid_history_is_rejected_before_model_execution(chat_setup, body):
    service, _ = chat_setup
    response = await post(body)
    assert response.status_code == 422
    service.assert_not_awaited()


async def test_initial_agent_failure_is_safe_http_error(chat_setup):
    service, _ = chat_setup
    service.side_effect = MaxTurnsExceeded("PRIVATE")
    response = await post({"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 502
    assert response.json() == {"detail": "Agent exceeded the maximum number of turns"}
    assert "PRIVATE" not in response.text
    assert response.headers["x-request-id"]


async def test_asgi_disconnect_closes_the_primed_stream(chat_setup):
    service, _ = chat_setup
    closed = asyncio.Event()
    sent_body = asyncio.Event()

    async def body():
        try:
            yield "partial\n"
            await asyncio.Event().wait()
        finally:
            closed.set()

    iterator = body()
    first = await anext(iterator)
    service.side_effect = None
    service.return_value = PreparedStream(first, iterator)
    payload = json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await sent_body.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            sent_body.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "http_version": "1.1",
        "scheme": "http",
        "method": "POST",
        "path": "/api/chat",
        "raw_path": b"/api/chat",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"content-type", b"application/json")],
        "client": ("test", 1),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), 2)
    assert closed.is_set()
