import asyncio
from typing import Annotated

from agents import MaxTurnsExceeded, RunConfig
from agents.sandbox import SandboxAgent, SandboxRunConfig
from agents.sandbox.sandboxes import UnixLocalSandboxClient
from asgi_correlation_id import CorrelationIdMiddleware, correlation_id
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from openai import APIError
from starlette.types import Receive, Scope, Send

from core.errors import public_error
from core.lifespan import lifespan
from core.middleware import RequestLoggingMiddleware
from dependencies import get_agent
from modules.chat_models import ChatRequest
from modules.chat_service import PreparedStream, stream_message

app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"X-Request-ID": correlation_id.get() or ""},
    )


@app.exception_handler(APIError)
@app.exception_handler(MaxTurnsExceeded)
async def agent_exception_handler(
    request: Request, exc: APIError | MaxTurnsExceeded
) -> JSONResponse:
    status_code, detail = public_error(exc)

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


class ChatStreamingResponse(StreamingResponse):
    def __init__(self, stream: PreparedStream):
        super().__init__(stream, media_type="application/x-ndjson")
        self.stream = stream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self.stream.aclose()


@app.post("/api/chat")
async def chat(body: ChatRequest, agent: AgentDep, request: Request):
    async def wait_for_disconnect():
        while (await request.receive())["type"] != "http.disconnect":
            pass

    run = asyncio.create_task(
        stream_message(
            body.to_agent_input(),
            agent=agent,
            run_config=RunConfig(
                sandbox=SandboxRunConfig(client=UnixLocalSandboxClient())
            ),
            max_turns=20,
        )
    )
    disconnect = asyncio.create_task(wait_for_disconnect())
    try:
        try:
            done, _ = await asyncio.wait(
                {run, disconnect}, return_when=asyncio.FIRST_COMPLETED
            )
            disconnected = disconnect in done
            if not disconnected:
                await (
                    run
                )  # Preserve the original exception for the HTTP error handlers.
        finally:
            disconnect.cancel()
            if not run.done():
                run.cancel()
            await asyncio.gather(run, disconnect, return_exceptions=True)
    except BaseException:
        if run.done() and not run.cancelled() and run.exception() is None:
            await run.result().aclose()
        raise

    if disconnected:
        if not run.cancelled() and run.exception() is None:
            await run.result().aclose()
        return Response(status_code=499)
    return ChatStreamingResponse(run.result())
