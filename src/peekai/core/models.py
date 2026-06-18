"""
Core data models for PeekAI tracing.

Hierarchy:
  Trace  — one full agent run
    └── Span  — one LLM call / tool call within that run
"""

from __future__ import annotations

import uuid
from contextvars import Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    PENDING = "pending"


class SpanKind(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    AGENT = "agent"
    CHAIN = "chain"


@dataclass
class Span:
    """
    Represents a single unit of work — typically one LLM call or tool call.
    """

    # Identity
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""
    parent_span_id: str | None = None  # for multi-agent / nested calls

    # Classification
    name: str = ""
    kind: SpanKind = SpanKind.LLM
    model: str = ""
    provider: str = ""  # "openai" | "anthropic" | "litellm"

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return delta.total_seconds() * 1000

    # I/O — stored as raw dicts, serialized to JSON in storage
    input: list[dict[str, Any]] = field(default_factory=list)   # messages sent
    output: str = ""                                             # assistant reply
    raw_response: dict[str, Any] = field(default_factory=dict)  # full API response

    # Token + cost tracking
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    # Tool calls (if the LLM requested tools)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    # Status + error
    status: SpanStatus = SpanStatus.PENDING
    error: str | None = None
    error_type: str | None = None

    # Arbitrary metadata attached by the user
    metadata: dict[str, Any] = field(default_factory=dict)

    # Internal: contextvar reset token, set by the Tracer when this span
    # becomes the active span. Used on finish to restore the parent span as
    # the active span rather than clearing the context. Not persisted.
    _token: Token[Span | None] | None = field(
        default=None, init=False, compare=False, repr=False
    )

    def finish(self, status: SpanStatus = SpanStatus.OK) -> None:
        """Mark the span as complete."""
        self.ended_at = datetime.now(timezone.utc)
        self.status = status

    def finish_with_error(self, exc: Exception) -> None:
        """Mark the span as failed and capture the exception."""
        self.ended_at = datetime.now(timezone.utc)
        self.status = SpanStatus.ERROR
        self.error = str(exc)
        self.error_type = type(exc).__name__


@dataclass
class Trace:
    """
    Represents one complete agent run, containing one or more spans.
    """

    # Identity
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "agent_run"

    # Timing
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        delta = self.ended_at - self.started_at
        return delta.total_seconds() * 1000

    # Spans collected during this run
    spans: list[Span] = field(default_factory=list)

    # Number of spans for this trace. Populated by list_traces (which omits the
    # spans themselves for performance) so summaries can show a count without a
    # full load. get_trace sets it to len(spans).
    span_count: int = 0

    # Rolled-up totals (computed on finish)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    # Status — derived from spans
    status: SpanStatus = SpanStatus.PENDING

    # Arbitrary metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_span(self, span: Span) -> None:
        span.trace_id = self.trace_id
        self.spans.append(span)

    def finish(self) -> None:
        """Close the trace and roll up token + cost totals from all spans."""
        self.ended_at = datetime.now(timezone.utc)
        self.total_input_tokens = sum(s.input_tokens for s in self.spans)
        self.total_output_tokens = sum(s.output_tokens for s in self.spans)
        self.total_tokens = sum(s.total_tokens for s in self.spans)
        self.total_cost_usd = sum(s.cost_usd for s in self.spans)
        has_error = any(s.status == SpanStatus.ERROR for s in self.spans)
        self.status = SpanStatus.ERROR if has_error else SpanStatus.OK
