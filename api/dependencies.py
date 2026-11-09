from agents import OpenAIChatCompletionsModel
from agents.sandbox import SandboxAgent
from fastapi import Request
from openai import AsyncOpenAI


def build_agent(client: AsyncOpenAI) -> SandboxAgent:
    model = OpenAIChatCompletionsModel(model="Model_Name", openai_client=client)

    return SandboxAgent(
        name="General assistant",
        instructions="Answer general questions.",
        model=model,
    )


def get_agent(request: Request) -> SandboxAgent:
    return build_agent(request.app.state.openai_client)
