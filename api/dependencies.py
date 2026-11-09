from agents import OpenAIChatCompletionsModel
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Compaction, Shell
from fastapi import Request
from openai import AsyncOpenAI

from modules.sandbox_tools import ChatCompletionsFilesystem


def build_agent(client: AsyncOpenAI, *, model: str, instructions: str) -> SandboxAgent:
    return SandboxAgent(
        name="OpenUI assistant",
        instructions=instructions,
        model=OpenAIChatCompletionsModel(model=model, openai_client=client),
        capabilities=[ChatCompletionsFilesystem(), Shell(), Compaction()],
    )


def get_agent(request: Request) -> SandboxAgent:
    return build_agent(
        request.app.state.openai_client,
        model=request.app.state.settings.OPENUI_MODEL,
        instructions=request.app.state.openui_prompt,
    )
