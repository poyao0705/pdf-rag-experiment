"""Exercise the actual SDK/sandbox boundary, replacing only network inference."""

import json
from pathlib import Path

import httpx2
import pytest
from agents import FunctionTool, RunConfig, TResponseInputItem
from agents.sandbox import SandboxRunConfig
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


@pytest.fixture
async def model_client():
    async def reject_network(request):
        raise AssertionError("An offline regression attempted a network request")

    transport = httpx2.MockTransport(reject_network)
    async with (
        httpx2.AsyncClient(transport=transport) as http,
        AsyncOpenAI(api_key="offline-test-key", http_client=http) as client,
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


async def test_real_runner_serializes_all_default_sandbox_tools(
    model_client, monkeypatch
):
    requests = []

    async def create(**kwargs):
        requests.append(kwargs)

        async def chunks():
            yield completion_chunk({"role": "assistant", "content": "Hello OpenUI"})
            yield completion_chunk({}, "stop")

        return chunks()

    monkeypatch.setattr(model_client.chat.completions, "create", create)
    agent = build_agent(
        model_client, model="test-model", instructions="]]>openui:config\n{}"
    )
    sandbox = RecordingSandboxClient()
    chunks = await run_chat(agent, sandbox)

    assert len(requests) == 1
    tools = {tool["function"]["name"]: tool for tool in requests[0]["tools"]}
    assert {"apply_patch", "view_image", "exec_command"} <= tools.keys()
    assert all(tool["type"] == "function" for tool in tools.values())
    assert (
        tools["apply_patch"]["function"]["parameters"]["properties"]["patch"]["type"]
        == "string"
    )
    assert {capability.type for capability in agent.capabilities} == {
        "filesystem",
        "shell",
        "compaction",
    }
    assert any(
        "]]>openui:config" in message.get("content", "")
        for message in requests[0]["messages"]
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
    model_client, monkeypatch, tmp_path, path
):
    from agents.sandbox import Manifest

    sandbox = RecordingSandboxClient()
    requests = []
    patch = f"*** Begin Patch\n*** Add File: {path}\n+Created through sandbox\n*** End Patch\n"

    async def create(**kwargs):
        requests.append(kwargs)

        async def chunks():
            if len(requests) == 1:
                yield completion_chunk(
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
                )
                yield completion_chunk({}, "tool_calls")
            else:
                output = [
                    message
                    for message in kwargs["messages"]
                    if message["role"] == "tool"
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
                yield completion_chunk({"role": "assistant", "content": "Finished"})
                yield completion_chunk({}, "stop")

        return chunks()

    monkeypatch.setattr(model_client.chat.completions, "create", create)
    agent = build_agent(
        model_client, model="test-model", instructions="Use your sandbox."
    )
    agent.default_manifest = Manifest(root=str(tmp_path / "workspace"))
    chunks = await run_chat(agent, sandbox)
    assert len(requests) == 2
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
