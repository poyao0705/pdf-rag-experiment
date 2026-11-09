from agents import RunConfig, Runner, Session
from agents.sandbox import SandboxAgent


async def send_message(
    message: str,
    *,
    agent: SandboxAgent,
    session: Session,
    run_config: RunConfig,
    max_turns: int = 20,
) -> str:
    result = await Runner.run(
        agent, message, session=session, run_config=run_config, max_turns=max_turns
    )
    return result.final_output
