from agents import OpenAIChatCompletionsModel
from agents.sandbox import SandboxAgent
from fastapi import Request
from openai import AsyncOpenAI


def build_agent(client: AsyncOpenAI, *, model: str, instructions: str) -> SandboxAgent:
    return SandboxAgent(
        name="OpenUI assistant",
        instructions=instructions,
        model=OpenAIChatCompletionsModel(model=model, openai_client=client),
    )


def get_agent(request: Request) -> SandboxAgent:
    return build_agent(
        request.app.state.openai_client,
        model=request.app.state.settings.OPENUI_MODEL,
        instructions=request.app.state.openui_prompt,
    )
