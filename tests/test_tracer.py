"""Unit tests for Tracer and the @trace / @tool decorators."""

from __future__ import annotations

import pytest

from peekai.core.models import SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer


@pytest.fixture
def storage(tmp_path):
    """In-memory-ish storage using a temp file."""
    db = tmp_path / "test.db"
    s = Storage(db)
    yield s
    s.close()


@pytest.fixture
def tracer(storage):
    return Tracer(storage=storage)


# ------------------------------------------------------------------
# Trace lifecycle
# ------------------------------------------------------------------

def test_start_and_finish_trace(tracer):
    t = tracer.start_trace("test_run")
    assert t.name == "test_run"
    assert t.status == SpanStatus.PENDING
    assert tracer.current_trace is t

    finished = tracer.finish_trace()
    assert finished is t
    assert t.ended_at is not None
    assert t.status == SpanStatus.OK
    assert tracer.current_trace is None


def test_trace_rolls_up_token_totals(tracer):
    t = tracer.start_trace("rollup_test")

    s1 = tracer.start_span("call1", model="gpt-4o", provider="openai")
    s1.input_tokens = 100
    s1.output_tokens = 50
    s1.total_tokens = 150
    s1.cost_usd = 0.001
    tracer.finish_span(s1)

    s2 = tracer.start_span("call2", model="gpt-4o", provider="openai")
    s2.input_tokens = 200
    s2.output_tokens = 80
    s2.total_tokens = 280
    s2.cost_usd = 0.002
    tracer.finish_span(s2)

    tracer.finish_trace(t)

    assert t.total_input_tokens == 300
    assert t.total_output_tokens == 130
    assert t.total_tokens == 430
    assert abs(t.total_cost_usd - 0.003) < 1e-9


def test_trace_status_is_error_if_any_span_fails(tracer):
    t = tracer.start_trace("error_test")
    span = tracer.start_span("bad_call")
    tracer.finish_span_with_error(span, ValueError("boom"))
    tracer.finish_trace(t)
    assert t.status == SpanStatus.ERROR


# ------------------------------------------------------------------
# Span lifecycle
# ------------------------------------------------------------------

def test_span_duration(tracer):
    tracer.start_trace("dur_test")
    span = tracer.start_span("timed_call")
    tracer.finish_span(span)
    assert span.duration_ms is not None
    assert span.duration_ms >= 0


def test_span_parent_child(tracer):
    tracer.start_trace("parent_child")
    parent = tracer.start_span("parent")
    child = tracer.start_span("child")
    assert child.parent_span_id == parent.span_id


# ------------------------------------------------------------------
# @trace decorator
# ------------------------------------------------------------------

def test_trace_decorator_sync(tracer, storage):
    @tracer.trace("decorated_run")
    def my_agent():
        return 42

    result = my_agent()
    assert result == 42

    traces = storage.list_traces()
    assert len(traces) == 1
    assert traces[0].name == "decorated_run"
    assert traces[0].status == SpanStatus.OK


def test_trace_decorator_propagates_exception(tracer):
    @tracer.trace("failing_run")
    def bad_agent():
        raise RuntimeError("agent failed")

    with pytest.raises(RuntimeError, match="agent failed"):
        bad_agent()


@pytest.mark.asyncio
async def test_trace_decorator_async(tracer, storage):
    @tracer.trace("async_run")
    async def async_agent():
        return "done"

    result = await async_agent()
    assert result == "done"

    traces = storage.list_traces()
    assert len(traces) == 1
    assert traces[0].status == SpanStatus.OK


# ------------------------------------------------------------------
# @tool decorator
# ------------------------------------------------------------------

def test_tool_decorator_creates_tool_span(tracer, storage):
    tracer.start_trace("tool_test")

    @tracer.tool("my_tool")
    def search(query: str) -> str:
        return f"results for {query}"

    result = search("peekai")
    assert result == "results for peekai"

    tracer.finish_trace()
    traces = storage.list_traces(limit=1)
    trace = storage.get_trace(traces[0].trace_id)
    assert trace is not None
    tool_spans = [s for s in trace.spans if s.kind == SpanKind.TOOL]
    assert len(tool_spans) == 1
    assert tool_spans[0].name == "my_tool"
