"""Unit tests for Tracer and the @trace / @tool decorators."""

from __future__ import annotations

import pytest

from peekai.core.models import SpanKind, SpanStatus
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


@pytest.fixture(autouse=True)
def _reset_context():
    """Reset the module-global trace/span contextvars around each test.

    The tracer stores the active trace and span in module-level ContextVars,
    so leftover state from one test could otherwise leak into the next.
    """
    import peekai.core.tracer as tracer_mod

    tracer_mod._active_trace.set(None)
    tracer_mod._active_span.set(None)
    yield
    tracer_mod._active_trace.set(None)
    tracer_mod._active_span.set(None)


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


# ------------------------------------------------------------------
# Parent/child context restoration (regression — contextvar bug)
# ------------------------------------------------------------------

def test_active_span_restored_to_parent_on_finish(tracer):
    """finish_span must restore the parent span, not clear the context."""
    tracer.start_trace("ctx")
    parent = tracer.start_span("parent", kind=SpanKind.AGENT)
    assert tracer.current_span is parent

    child = tracer.start_span("child", kind=SpanKind.LLM)
    assert tracer.current_span is child

    tracer.finish_span(child)
    # Regression: previously this reset the active span to None.
    assert tracer.current_span is parent

    tracer.finish_span(parent)
    assert tracer.current_span is None


def test_sequential_spans_inside_agent_share_parent(tracer):
    """Every LLM call inside one agent must be a child of that agent.

    Regression: the 2nd+ call used to lose its parent because finish_span
    cleared the active span instead of restoring the agent span.
    """
    captured: dict[str, object] = {}

    @tracer.agent("worker")
    def worker() -> None:
        captured["agent"] = tracer.current_span
        s1 = tracer.start_span("llm1", kind=SpanKind.LLM)
        tracer.finish_span(s1)
        s2 = tracer.start_span("llm2", kind=SpanKind.LLM)
        tracer.finish_span(s2)
        captured["s1"] = s1
        captured["s2"] = s2

    @tracer.trace("run")
    def run() -> None:
        worker()

    run()

    agent_span = captured["agent"]
    assert captured["s1"].parent_span_id == agent_span.span_id  # type: ignore[union-attr]
    assert captured["s2"].parent_span_id == agent_span.span_id  # type: ignore[union-attr]


def test_sibling_agents_are_not_nested(tracer, storage):
    """Sequential sibling agents must both be roots, not nested.

    Regression: the second agent ("writer") used to be parented under the
    first ("researcher") because the active span was never restored.
    """
    @tracer.agent("researcher")
    def researcher() -> str:
        return "r"

    @tracer.agent("writer")
    def writer() -> str:
        return "w"

    @tracer.trace("pipeline")
    def run() -> None:
        researcher()
        writer()

    run()

    traces = storage.list_traces(limit=1)
    trace = storage.get_trace(traces[0].trace_id)
    assert trace is not None
    by_name = {s.name: s for s in trace.spans}

    assert by_name["researcher"].parent_span_id is None
    assert by_name["writer"].parent_span_id is None
    assert by_name["writer"].parent_span_id != by_name["researcher"].span_id


# ------------------------------------------------------------------
# Implicit "auto" trace (regression — no active trace crashed)
# ------------------------------------------------------------------

def test_span_without_active_trace_is_captured(tracer, storage):
    """A span started with no @trace active must be captured, not crash.

    Regression: previously this raised `FOREIGN KEY constraint failed` because
    the span had an empty trace_id with no matching trace row — which broke the
    documented `peekai.init()` quickstart that makes a bare LLM call.
    """
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM)
    span.input_tokens, span.output_tokens, span.total_tokens = 10, 5, 15
    span.cost_usd = 0.001
    tracer.finish_span(span)  # must not raise

    traces = storage.list_traces()
    assert len(traces) == 1
    full = storage.get_trace(traces[0].trace_id)
    assert full is not None
    assert len(full.spans) == 1
    assert full.spans[0].name == "openai/gpt-4o"
    # The implicit trace is rolled up so totals/status are meaningful.
    assert full.total_tokens == 15
    assert full.status == SpanStatus.OK


def test_multiple_orphan_spans_share_one_auto_trace(tracer, storage):
    """Sequential calls with no @trace group under a single implicit trace."""
    for _ in range(3):
        s = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM)
        tracer.finish_span(s)

    traces = storage.list_traces()
    assert len(traces) == 1
    full = storage.get_trace(traces[0].trace_id)
    assert full is not None
    assert len(full.spans) == 3


# ------------------------------------------------------------------
# Instrumentation must never break user code
# ------------------------------------------------------------------

def test_finish_span_does_not_raise_on_storage_error(tracer, storage, monkeypatch):
    """A storage failure during finish must be swallowed, not propagated."""
    tracer.start_trace("t")
    span = tracer.start_span("call", kind=SpanKind.LLM)

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(storage, "save_span", boom)

    # Must complete normally — tracing failures cannot break the traced program.
    tracer.finish_span(span)
    # Context is still restored despite the save failure.
    assert tracer.current_span is None
