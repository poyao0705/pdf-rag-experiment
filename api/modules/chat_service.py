import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from uuid import uuid4

from agents import RunConfig, Runner, TResponseInputItem
from agents.sandbox import SandboxAgent

from core.errors import public_error

logger = logging.getLogger(__name__)


class PreparedStream(AsyncIterator[str]):
    """Own a primed generator, including when closed before its first iteration."""

    def __init__(self, first: str, body: AsyncGenerator[str, None]):
        self._first: str | None = first
        self._body = body

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if self._first is not None:
            first, self._first = self._first, None
            return first
        return await anext(self._body)

    async def aclose(self) -> None:
        self._first = None
        await self._body.aclose()


async def stream_message(
    messages: list[TResponseInputItem],
    *,
    agent: SandboxAgent,
    run_config: RunConfig,
    max_turns: int = 20,
) -> PreparedStream:
    result = Runner.run_streamed(
        agent, messages, run_config=run_config, max_turns=max_turns
    )
    events = result.stream_events()
    response_id = f"chatcmpl-{uuid4().hex}"
    model = (
        agent.model
        if isinstance(agent.model, str)
        else getattr(agent.model, "model", "unknown")
    )
    created = int(time.time())

    def chunk(delta: dict, finish: str | None = None) -> str:
        return (
            json.dumps(
                {
                    "id": response_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                }
            )
            + "\n"
        )

    async def body() -> AsyncGenerator[str, None]:
        started = False
        try:
            async for event in events:
                if (
                    event.type != "raw_response_event"
                    or event.data.type != "response.output_text.delta"
                ):
                    continue
                if not event.data.delta:
                    continue
                if not started:
                    started = True
                    yield chunk({"role": "assistant"})
                yield chunk({"content": event.data.delta})
            if not started:
                started = True
                yield chunk({"role": "assistant"})
            yield chunk({}, "stop")
        except Exception as exc:
            if not started:
                raise
            logger.exception("Agent stream failed")
            _, message = public_error(exc)
            yield (
                json.dumps({"error": {"message": message, "type": "stream_error"}})
                + "\n"
            )
        finally:
            if not result.is_complete:
                result.cancel()
            close = getattr(events, "aclose", None)
            if close is not None:
                await close()

    iterator = body()
    try:
        first = await anext(iterator)
    except BaseException:
        await iterator.aclose()
        raise
    return PreparedStream(first, iterator)

