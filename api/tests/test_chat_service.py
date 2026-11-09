import asyncio
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents import MaxTurnsExceeded, RunConfig

from modules.chat_service import stream_message

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text(value):
    return SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(type="response.output_text.delta", delta=value),
    )


class FakeResult:
    def __init__(self, events):
        self.events = events
        self.is_complete = False
        self.cancelled = False
        self.closed = asyncio.Event()
        self.waiting = asyncio.Event()

    def cancel(self):
        self.cancelled = True

    async def stream_events(self):
        try:
            for event in self.events:
                if event == "wait":
                    self.waiting.set()
                    await asyncio.Event().wait()
                if isinstance(event, Exception):
                    raise event
                yield event
            self.is_complete = True
        finally:
            await asyncio.sleep(0)
            self.closed.set()


@pytest.fixture
def setup_run(monkeypatch):
    def setup(events):
        result = FakeResult(events)
        runner = Mock(return_value=result)
        monkeypatch.setattr("modules.chat_service.Runner.run_streamed", runner)
        agent = SimpleNamespace(model=SimpleNamespace(model="configured-model"))
        config = RunConfig()
        return result, runner, agent, config

    return setup


async def test_streams_ordered_text_and_one_final_finish(setup_run):
    result, runner, agent, config = setup_run([text("one"), text("二")])
    messages = [{"role": "user", "content": "real prompt"}]
    stream = await stream_message(messages, agent=agent, run_config=config)
    chunks = [json.loads(line) async for line in stream]
    runner.assert_called_once_with(agent, messages, run_config=config, max_turns=20)
    assert len({c["id"] for c in chunks}) == 1
    assert {c["model"] for c in chunks} == {"configured-model"}
    assert chunks[0]["choices"][0]["delta"] == {"role": "assistant"}
    assert [c["choices"][0]["delta"].get("content") for c in chunks[1:-1]] == [
        "one",
        "二",
    ]
    assert [c["choices"][0]["finish_reason"] for c in chunks] == [
        None,
        None,
        None,
        "stop",
    ]
    assert result.closed.is_set()
    assert not result.cancelled


async def test_tool_turn_does_not_finish_chat_or_expose_private_events(setup_run):
    private = SimpleNamespace(
        type="raw_response_event",
        data=SimpleNamespace(
            type="response.function_call_arguments.delta", delta="PRIVATE"
        ),
    )
    intermediate = SimpleNamespace(
        type="raw_response_event", data=SimpleNamespace(type="response.completed")
    )
    result, _, agent, config = setup_run(
        [
            text("before"),
            private,
            intermediate,
            SimpleNamespace(type="run_item_stream_event"),
            text("after"),
        ]
    )
    stream = await stream_message([], agent=agent, run_config=config)
    lines = [line async for line in stream]
    assert "PRIVATE" not in "".join(lines)
    assert sum('"stop"' in line for line in lines) == 1
    assert "after" in lines[-2]
    assert result.is_complete


async def test_initial_error_is_raised_before_body_is_returned(setup_run):
    result, _, agent, config = setup_run([MaxTurnsExceeded("PRIVATE")])
    with pytest.raises(MaxTurnsExceeded):
        await stream_message([], agent=agent, run_config=config)
    assert result.cancelled
    assert result.closed.is_set()


async def test_midstream_error_is_safe_and_has_no_stop_chunk(setup_run):
    result, _, agent, config = setup_run([text("partial"), MaxTurnsExceeded("PRIVATE")])
    stream = await stream_message([], agent=agent, run_config=config)
    lines = [json.loads(line) async for line in stream]
    assert lines[-1] == {
        "error": {
            "message": "Agent exceeded the maximum number of turns",
            "type": "stream_error",
        }
    }
    assert "PRIVATE" not in json.dumps(lines)
    assert '"stop"' not in json.dumps(lines)
    assert result.cancelled


async def test_cancel_before_first_text_cleans_up(setup_run):
    result, _, agent, config = setup_run(["wait"])
    task = asyncio.create_task(stream_message([], agent=agent, run_config=config))
    await asyncio.wait_for(result.waiting.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert result.cancelled
    assert result.closed.is_set()


@pytest.mark.parametrize("consume", [False, True])
async def test_close_after_priming_cancels_and_closes_iterator(setup_run, consume):
    result, _, agent, config = setup_run([text("partial"), "wait"])
    stream = await stream_message([], agent=agent, run_config=config)
    if consume:
        await anext(stream)
        await anext(stream)
    await stream.aclose()
    assert result.cancelled
    assert result.closed.is_set()
