from typing import Annotated

from agents import MaxTurnsExceeded, RunConfig, SQLiteSession
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.sandboxes import UnixLocalSandboxClient
from asgi_correlation_id import CorrelationIdMiddleware, correlation_id
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from openai import APITimeoutError, RateLimitError

from core.lifespan import lifespan
from core.middleware import RequestLoggingMiddleware
from dependencies import get_agent
from modules.chat_service import send_message

app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-ID": correlation_id.get() or ""},
    )


@app.exception_handler(APITimeoutError)
@app.exception_handler(RateLimitError)
@app.exception_handler(MaxTurnsExceeded)
async def agent_exception_handler(
    request: Request, exc: APITimeoutError | RateLimitError | MaxTurnsExceeded
) -> JSONResponse:
    if isinstance(exc, APITimeoutError):
        status_code = 504
        detail = "Model request timed out"
    elif isinstance(exc, RateLimitError):
        status_code = 503
        detail = "Model service temporarily unavailable"
    else:
        status_code = 502
        detail = "Agent exceeded the maximum number of turns"

    # Handled responses pass through the middleware that adds the request ID.
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)


@app.get("/")
def main():
    return {"message": "Hello World"}


AgentDep = Annotated[SandboxAgent, Depends(get_agent)]


@app.post("/api/chat")
async def chat(body: dict, agent: AgentDep):
    # messages = body.get("messages", []) # TODO: replace this with actual message store in the future
    session_id = body.get("session_id", "user_default")
    messages = "Come up with mock financial data, and respond with annual report analysis"  # placeholder
    session = SQLiteSession(session_id)
    result = await send_message(
        messages,
        agent=agent,
        session=session,
        run_config=RunConfig(sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())),
        max_turns=20,
    )
    return result
