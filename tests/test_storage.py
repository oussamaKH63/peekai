"""Unit tests for the SQLite Storage layer."""

from __future__ import annotations

import pytest

from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage


@pytest.fixture
def storage(tmp_path):
    db = tmp_path / "test.db"
    s = Storage(db)
    yield s
    s.close()


def _make_trace(name: str = "test_run") -> Trace:
    t = Trace(name=name)
    t.finish()
    return t


def _make_span(trace_id: str, model: str = "gpt-4o") -> Span:
    s = Span(
        trace_id=trace_id,
        name=f"openai/{model}",
        kind=SpanKind.LLM,
        model=model,
        provider="openai",
        input=[{"role": "user", "content": "hello"}],
        output="hi there",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.0001,
    )
    s.finish()
    return s


# ------------------------------------------------------------------
# Trace CRUD
# ------------------------------------------------------------------

def test_save_and_get_trace(storage):
    t = _make_trace("my_run")
    storage.save_trace(t)

    fetched = storage.get_trace(t.trace_id)
    assert fetched is not None
    assert fetched.trace_id == t.trace_id
    assert fetched.name == "my_run"


def test_get_trace_returns_none_for_unknown(storage):
    assert storage.get_trace("nonexistent-id") is None


def test_list_traces_returns_most_recent_first(storage):
    for i in range(5):
        storage.save_trace(_make_trace(f"run_{i}"))

    traces = storage.list_traces(limit=3)
    assert len(traces) == 3


def test_delete_all_wipes_everything(storage):
    storage.save_trace(_make_trace())
    storage.delete_all()
    assert storage.list_traces() == []


# ------------------------------------------------------------------
# Span CRUD
# ------------------------------------------------------------------

def test_save_and_get_span(storage):
    t = _make_trace()
    storage.save_trace(t)

    span = _make_span(t.trace_id)
    storage.save_span(span)

    spans = storage.get_spans(t.trace_id)
    assert len(spans) == 1
    assert spans[0].span_id == span.span_id
    assert spans[0].model == "gpt-4o"
    assert spans[0].input_tokens == 10
    assert spans[0].output == "hi there"


def test_get_trace_includes_spans(storage):
    t = _make_trace()
    storage.save_trace(t)
    storage.save_span(_make_span(t.trace_id))
    storage.save_span(_make_span(t.trace_id, model="gpt-4o-mini"))

    fetched = storage.get_trace(t.trace_id)
    assert fetched is not None
    assert len(fetched.spans) == 2


# ------------------------------------------------------------------
# Stats
# ------------------------------------------------------------------

def test_stats_aggregation(storage):
    for _ in range(3):
        t = _make_trace()
        t.total_tokens = 100
        t.total_cost_usd = 0.01
        storage.save_trace(t)

    stats = storage.get_stats()
    assert stats["total_runs"] == 3
    assert stats["total_tokens"] == 300
    assert abs(stats["total_cost_usd"] - 0.03) < 1e-9


# ------------------------------------------------------------------
# Serialisation round-trip
# ------------------------------------------------------------------

def test_span_json_fields_round_trip(storage):
    t = _make_trace()
    storage.save_trace(t)

    span = _make_span(t.trace_id)
    span.tool_calls = [{"id": "tc_1", "function": "search", "arguments": '{"q":"test"}'}]
    span.metadata = {"custom_key": "custom_value"}
    storage.save_span(span)

    fetched = storage.get_spans(t.trace_id)[0]
    assert fetched.tool_calls[0]["function"] == "search"
    assert fetched.metadata["custom_key"] == "custom_value"
