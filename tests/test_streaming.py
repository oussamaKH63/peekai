"""Tests for streaming-response capture (accumulators + transparent proxy)."""

from __future__ import annotations

import types

import pytest

from peekai.core.models import SpanKind, SpanStatus
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer
from peekai.patches._stream import (
    AnthropicAccumulator,
    AsyncTracedMessageStreamManager,
    OpenAIAccumulator,
    TracedMessageStreamManager,
    wrap_sync,
)


@pytest.fixture(autouse=True)
def _reset_context():
    import peekai.core.tracer as tracer_mod

    tracer_mod._active_trace.set(None)
    tracer_mod._active_span.set(None)
    yield
    tracer_mod._active_trace.set(None)
    tracer_mod._active_span.set(None)


@pytest.fixture
def tracer(tmp_path):
    return Tracer(storage=Storage(tmp_path / "stream.db"))


def _oa_chunk(content=None, usage=None):
    delta = types.SimpleNamespace(content=content, tool_calls=None)
    choice = types.SimpleNamespace(delta=delta)
    return types.SimpleNamespace(choices=[choice], usage=usage)


def _started_span(
    tracer, name="openai/gpt-4o", model="gpt-4o", provider="openai"
):
    """Mimic what a patch does for a streaming call: start then finish-now."""
    tracer.start_trace("t")
    span = tracer.start_span(name, kind=SpanKind.LLM, model=model, provider=provider)
    tracer.finish_span(span, SpanStatus.OK)
    return span


def test_openai_stream_accumulates_output_and_usage(tracer):
    span = _started_span(tracer)
    usage = types.SimpleNamespace(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    chunks = [_oa_chunk("Hello"), _oa_chunk(" world"), _oa_chunk(usage=usage)]

    stream = wrap_sync(iter(chunks), span, OpenAIAccumulator(), "gpt-4o", tracer)
    received = list(stream)  # consume like user code

    # The proxy yields the original chunks untouched.
    assert received[0].choices[0].delta.content == "Hello"

    saved = tracer.storage.get_spans(span.trace_id)[0]
    assert saved.output == "Hello world"
    assert saved.total_tokens == 15
    assert saved.cost_usd > 0
    assert saved.metadata.get("streaming") is True


def test_anthropic_stream_accumulates_text_and_usage(tracer):
    span = _started_span(
        tracer, name="anthropic/claude", model="claude-3-5-sonnet-20241022",
        provider="anthropic",
    )
    events = [
        types.SimpleNamespace(
            type="message_start",
            message=types.SimpleNamespace(usage=types.SimpleNamespace(input_tokens=12)),
        ),
        types.SimpleNamespace(
            type="content_block_delta", delta=types.SimpleNamespace(text="Hi ")
        ),
        types.SimpleNamespace(
            type="content_block_delta", delta=types.SimpleNamespace(text="there")
        ),
        types.SimpleNamespace(
            type="message_delta", usage=types.SimpleNamespace(output_tokens=7)
        ),
    ]
    stream = wrap_sync(
        iter(events), span, AnthropicAccumulator(), "claude-3-5-sonnet-20241022", tracer
    )
    list(stream)

    saved = tracer.storage.get_spans(span.trace_id)[0]
    assert saved.output == "Hi there"
    assert saved.input_tokens == 12
    assert saved.output_tokens == 7
    assert saved.total_tokens == 19


def test_stream_error_is_recorded_and_reraised(tracer):
    span = _started_span(tracer)

    def gen():
        yield _oa_chunk("partial")
        raise RuntimeError("stream broke")

    stream = wrap_sync(gen(), span, OpenAIAccumulator(), "gpt-4o", tracer)
    with pytest.raises(RuntimeError, match="stream broke"):
        list(stream)

    saved = tracer.storage.get_spans(span.trace_id)[0]
    assert saved.status == SpanStatus.ERROR
    assert "stream broke" in (saved.error or "")
    assert saved.output == "partial"  # partial output still captured


def test_proxy_delegates_attributes_to_underlying_stream(tracer):
    span = _started_span(tracer)

    class FakeStream:
        response = "the-http-response"
        def __iter__(self):
            return iter([_oa_chunk("x")])

    stream = wrap_sync(FakeStream(), span, OpenAIAccumulator(), "gpt-4o", tracer)
    # Unknown attribute is delegated to the wrapped stream.
    assert stream.response == "the-http-response"
    list(stream)


# ---------------------------------------------------------------------------
# TracedMessageStreamManager — covers client.messages.stream() path
# ---------------------------------------------------------------------------

def _anthropic_events():
    """Minimal sequence of Anthropic SSE events emitted by MessageStream.__iter__."""
    return [
        types.SimpleNamespace(
            type="message_start",
            message=types.SimpleNamespace(usage=types.SimpleNamespace(input_tokens=8)),
        ),
        types.SimpleNamespace(
            type="content_block_delta", delta=types.SimpleNamespace(text="Hello ")
        ),
        types.SimpleNamespace(
            type="content_block_delta", delta=types.SimpleNamespace(text="world")
        ),
        types.SimpleNamespace(
            type="message_delta", usage=types.SimpleNamespace(output_tokens=5)
        ),
    ]


class _FakeMessageStream:
    """Minimal stand-in for anthropic.MessageStream."""

    def __init__(self, events):
        self._events = events

    def __iter__(self):
        return iter(self._events)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def close(self):
        pass


class _FakeMessageStreamManager:
    """Minimal stand-in for anthropic.MessageStreamManager."""

    def __init__(self, events):
        self._events = events

    def __enter__(self):
        return _FakeMessageStream(self._events)

    def __exit__(self, *_):
        pass


class _FakeAsyncMessageStream:
    """Async version of _FakeMessageStream."""

    def __init__(self, events):
        self._events = events

    async def __aiter__(self):
        for event in self._events:
            yield event

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def aclose(self):
        pass


class _FakeAsyncMessageStreamManager:
    """Async version of _FakeMessageStreamManager."""

    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return _FakeAsyncMessageStream(self._events)

    async def __aexit__(self, *_):
        pass


def test_traced_message_stream_manager_captures_text_and_usage(tracer):
    tracer.start_trace("t")
    span = tracer.start_span(
        "anthropic/claude", kind=SpanKind.LLM,
        model="claude-3-5-sonnet-20241022", provider="anthropic",
    )
    tracer.finish_span(span, SpanStatus.OK)

    manager = _FakeMessageStreamManager(_anthropic_events())
    traced = TracedMessageStreamManager(manager, span, "claude-3-5-sonnet-20241022", tracer)

    with traced as stream:
        output = "".join(
            event.delta.text
            for event in stream
            if event.type == "content_block_delta"
        )

    assert output == "Hello world"

    saved = tracer.storage.get_spans(span.trace_id)[0]
    assert saved.output == "Hello world"
    assert saved.input_tokens == 8
    assert saved.output_tokens == 5
    assert saved.total_tokens == 13
    assert saved.metadata.get("streaming") is True


@pytest.mark.asyncio
async def test_async_traced_message_stream_manager_captures_text_and_usage(tracer):
    tracer.start_trace("t")
    span = tracer.start_span(
        "anthropic/claude", kind=SpanKind.LLM,
        model="claude-3-5-sonnet-20241022", provider="anthropic",
    )
    tracer.finish_span(span, SpanStatus.OK)

    manager = _FakeAsyncMessageStreamManager(_anthropic_events())
    traced = AsyncTracedMessageStreamManager(manager, span, "claude-3-5-sonnet-20241022", tracer)

    collected = []
    async with traced as stream:
        async for event in stream:
            if event.type == "content_block_delta":
                collected.append(event.delta.text)

    assert "".join(collected) == "Hello world"

    saved = tracer.storage.get_spans(span.trace_id)[0]
    assert saved.output == "Hello world"
    assert saved.input_tokens == 8
    assert saved.output_tokens == 5
    assert saved.total_tokens == 13
    assert saved.metadata.get("streaming") is True
