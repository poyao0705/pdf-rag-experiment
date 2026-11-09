import json

import pytest
from agents import ModelSettings, OpenAIChatCompletionsModel, RunContextWrapper
from agents.models.interface import ModelTracing
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from dependencies import build_agent
from modules.openui import cloud_system_prompt


def write_spec(path):
    path.write_text(
        json.dumps(
            {
                "schema": {"type": "object"},
                "root": "Stack",
                "componentGroups": [],
                "id": None,
                "components": {"private": True},
            }
        )
    )
    return path


def test_cloud_prompt_uses_only_library_config_and_form_rules(tmp_path):
    prompt = cloud_system_prompt(write_spec(tmp_path / "spec.json"))
    marker, config, rules = prompt.split("\n", 2)
    assert marker == "]]>openui:config"
    assert json.loads(config) == {
        "chatLibrary": {
            "schema": {"type": "object"},
            "root": "Stack",
            "componentGroups": [],
        }
    }
    assert "@ToAssistant" in rules
    assert "$tripType" in rules


@pytest.mark.parametrize(
    "content",
    [
        None,
        "{",
        "[]",
        "{}",
        '{"root":"Stack","schema":{}}',
        '{"root":7,"schema":{"type":"object"}}',
    ],
)
def test_missing_or_invalid_spec_has_actionable_error(tmp_path, content):
    path = tmp_path / "spec.json"
    if content is not None:
        path.write_text(content)
    with pytest.raises(RuntimeError, match="vp run generate"):
        cloud_system_prompt(path)


@pytest.mark.anyio
async def test_agent_uses_configured_model_and_cloud_instructions(
    tmp_path, monkeypatch
):
    client = AsyncOpenAI(api_key="test-key", base_url="https://example.test/v1")
    instructions = cloud_system_prompt(write_spec(tmp_path / "spec.json"))
    agent = build_agent(client, model="configured-model", instructions=instructions)
    captured = {}

    async def create(**kwargs):
        captured.update(kwargs)
        return ChatCompletion.model_validate(
            {
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "configured-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            }
        )

    monkeypatch.setattr(client.chat.completions, "create", create)
    try:
        prompt = await agent.get_system_prompt(RunContextWrapper(context=None))
        assert isinstance(agent.model, OpenAIChatCompletionsModel)
        await agent.model.get_response(
            prompt, "hello", ModelSettings(), [], None, [], ModelTracing.DISABLED
        )
        assert captured["model"] == "configured-model"
        assert instructions in captured["messages"][0]["content"]
    finally:
        await client.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
