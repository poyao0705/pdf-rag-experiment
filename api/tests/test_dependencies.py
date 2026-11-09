from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from openai import AsyncOpenAI
from pydantic import SecretStr

import core.lifespan as lifespan_module
from dependencies import get_agent

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        lifespan_module,
        "get_settings",
        lambda: SimpleNamespace(
            LOG_LEVEL="INFO",
            THESYS_API_KEY=SecretStr("test-api-key"),
            OPENUI_MODEL="test-model",
            OPENUI_SPEC_PATH=Path("unused-test-spec"),
            THESYS_BASE_URL="https://example.test/v1",
        ),
    )
    monkeypatch.setattr(lifespan_module, "configure_logging", lambda level: None)
    monkeypatch.setattr(
        lifespan_module,
        "cloud_system_prompt",
        lambda path: "test prompt",
        raising=False,
    )
    return FastAPI(lifespan=lifespan_module.lifespan)


async def test_get_agent_creates_a_fresh_agent_for_each_request(app):
    async with app.router.lifespan_context(app):
        first = get_agent(Request({"type": "http", "app": app}))
        second = get_agent(Request({"type": "http", "app": app}))

        assert first is not second


async def test_lifespan_keeps_the_shared_client_open_until_shutdown(app):
    async with app.router.lifespan_context(app):
        client = getattr(app.state, "openai_client", None)

        assert isinstance(client, AsyncOpenAI)
        assert not client.is_closed()

    assert client.is_closed()
