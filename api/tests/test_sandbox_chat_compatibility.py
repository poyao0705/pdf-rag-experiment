"""Exercise the real SDK and sandbox, replacing only the HTTP transport."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2
import pytest
from agents import FunctionTool, RunConfig, TResponseInputItem
from agents.sandbox import Manifest, SandboxRunConfig
from agents.sandbox.sandboxes import UnixLocalSandboxClient
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from dependencies import build_agent
from modules.chat_service import stream_message
from modules.sandbox_tools import ChatCompletionsFilesystem

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


class RecordingSandboxClient(UnixLocalSandboxClient):
    def __init__(self):
        super().__init__(inherit_host_environment=False)
        self.created = []

    async def create(self, **kwargs):
        session = await super().create(**kwargs)
        self.created.append(session)
        return session


def completion_chunk(delta, finish=None):
    return ChatCompletionChunk.model_validate(
        {
            "id": "fake-completion",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test-model",
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
    )


class FakeGateway:
    def __init__(self):
        self.requests: list[dict[str, Any]] = []
        self.respond: Callable[[dict[str, Any]], list[ChatCompletionChunk]] | None = (
            None
        )

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/embed/chat/completions"
        payload = json.loads(request.content)
        self.requests.append(payload)
        assert self.respond is not None
        chunks = self.respond(payload)
        content = "".join(f"data: {chunk.model_dump_json()}\n\n" for chunk in chunks)
        return httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=content + "data: [DONE]\n\n",
        )


@pytest.fixture
def gateway():
    return FakeGateway()


@pytest.fixture
async def model_client(gateway):
    # Do not replace .create(): its real argument validation must run.
    async with (
        httpx2.AsyncClient(transport=httpx2.MockTransport(gateway)) as http,
        AsyncOpenAI(
            api_key="offline-test-key",
            base_url="https://gateway.test/v1/embed",
            http_client=http,
        ) as client,
    ):
        yield client


async def run_chat(agent, sandbox):
    messages: list[TResponseInputItem] = [
        {"role": "user", "content": "Use the sandbox and answer."}
    ]
    stream = await stream_message(
        messages,
        agent=agent,
        run_config=RunConfig(
            tracing_disabled=True,
            sandbox=SandboxRunConfig(client=sandbox),
        ),
    )
    return [json.loads(line) async for line in stream]


async def test_real_client_streams_with_sandbox_tools_without_responses_only_options(
    model_client, gateway
):
    gateway.respond = lambda payload: [
        completion_chunk({"role": "assistant", "content": "Hello OpenUI"}),
        completion_chunk({}, "stop"),
    ]
    agent = build_agent(
        model_client, model="test-model", instructions="]]>openui:config\n{}"
    )
    sandbox = RecordingSandboxClient()
    chunks = await run_chat(agent, sandbox)

    assert len(gateway.requests) == 1
    request = gateway.requests[0]
    assert "context_management" not in request
    tools = {tool["function"]["name"]: tool for tool in request["tools"]}
    assert {"apply_patch", "view_image", "exec_command"} <= tools.keys()
    assert all(tool["type"] == "function" for tool in tools.values())
    assert (
        tools["apply_patch"]["function"]["parameters"]["properties"]["patch"]["type"]
        == "string"
    )
    assert {capability.type for capability in agent.capabilities} == {
        "filesystem",
        "shell",
    }
    assert any(
        "]]>openui:config" in message.get("content", "")
        for message in request["messages"]
        if message["role"] == "system"
    )
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert any(
        chunk["choices"][0]["delta"].get("content") == "Hello OpenUI"
        for chunk in chunks
    )
    assert sandbox.created
    assert all(
        not Path(session.state.manifest.root).exists() for session in sandbox.created
    )


@pytest.mark.parametrize("path", ["note.txt", "../escaped-note.txt"])
async def test_real_runner_executes_json_patch_with_original_workspace_guard(
    model_client, gateway, tmp_path, path
):
    sandbox = RecordingSandboxClient()
    patch = f"*** Begin Patch\n*** Add File: {path}\n+Created through sandbox\n*** End Patch\n"

    def respond(payload):
        if len(gateway.requests) == 1:
            return [
                completion_chunk(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-patch",
                                "type": "function",
                                "function": {
                                    "name": "apply_patch",
                                    "arguments": json.dumps({"patch": patch}),
                                },
                            }
                        ],
                    }
                ),
                completion_chunk({}, "tool_calls"),
            ]
        output = [
            message for message in payload["messages"] if message["role"] == "tool"
        ]
        assert len(output) == 1
        assert output[0]["tool_call_id"] == "call-patch"
        if path == "note.txt":
            assert (
                tmp_path / "workspace" / path
            ).read_text() == "Created through sandbox"
        else:
            assert not (tmp_path / "escaped-note.txt").exists()
            assert "error" in output[0]["content"].lower()
        return [
            completion_chunk({"role": "assistant", "content": "Finished"}),
            completion_chunk({}, "stop"),
        ]

    gateway.respond = respond
    agent = build_agent(
        model_client, model="test-model", instructions="Use your sandbox."
    )
    agent.default_manifest = Manifest(root=str(tmp_path / "workspace"))
    chunks = await run_chat(agent, sandbox)
    assert len(gateway.requests) == 2
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert all("call-patch" not in json.dumps(chunk) for chunk in chunks)


@pytest.mark.parametrize("policy", [False, True, "callback"])
async def test_patch_adapter_preserves_boolean_approvals_and_rejects_unsupported_callbacks(
    policy,
):
    async def on_approval(*args, **kwargs):
        pass

    def configure(toolset):
        if policy == "callback":
            toolset.apply_patch.on_approval = on_approval
        else:
            toolset.apply_patch.needs_approval = policy

    async with await RecordingSandboxClient().create() as session:
        capability = ChatCompletionsFilesystem(configure_tools=configure)
        capability.bind(session)
        if policy == "callback":
            with pytest.raises(ValueError, match="approval callbacks"):
                capability.tools()
        else:
            patch = next(
                tool for tool in capability.tools() if tool.name == "apply_patch"
            )
            assert isinstance(patch, FunctionTool)
            assert patch.needs_approval is policy
