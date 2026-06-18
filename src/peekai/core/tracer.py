"""
Tracer — manages the active Trace and Span lifecycle.

Uses contextvars so it is safe in async / multi-threaded code.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage

logger = logging.getLogger("peekai")

# Context variables — one active trace and one active span per async context
_active_trace: ContextVar[Trace | None] = ContextVar("_active_trace", default=None)
_active_span: ContextVar[Span | None] = ContextVar("_active_span", default=None)

# Name + metadata flag for traces created implicitly when a span starts with no
# explicit @trace active, so auto-instrumented calls are still captured instead
# of producing orphan spans.
_AUTO_TRACE_NAME = "auto"
_AUTO_TRACE_FLAG = "peekai_auto"


class Tracer:
    """
    Central tracer that creates traces/spans and persists them to storage.
    """

    def __init__(self, storage: Storage | None = None, db_path: str | Path | None = None) -> None:
        self.storage = storage or Storage(db_path)

    # ------------------------------------------------------------------
    # Trace lifecycle
    # ------------------------------------------------------------------

    def start_trace(self, name: str = "agent_run", metadata: dict[str, Any] | None = None) -> Trace:
        """Create and register a new Trace as the active trace."""
        trace = Trace(name=name, metadata=metadata or {})
        _active_trace.set(trace)
        self._save_trace_safe(trace)
        return trace

    def finish_trace(self, trace: Trace | None = None) -> Trace | None:
        """Finish the given trace (or the active one) and persist it."""
        t = trace or _active_trace.get()
        if t is None:
            return None
        t.finish()
        self._save_trace_safe(t)
        _active_trace.set(None)
        return t

    # ------------------------------------------------------------------
    # Span lifecycle
    # ------------------------------------------------------------------

    def start_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.LLM,
        model: str = "",
        provider: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Span:
        """Create a new Span and attach it to the active Trace."""
        trace = _active_trace.get()
        if trace is None:
            # No explicit @trace is active (e.g. peekai.init() was called but
            # this call site isn't wrapped in @trace). Create an implicit "auto"
            # trace so the call is still captured instead of producing an orphan
            # span that would violate the spans→traces foreign key.
            trace = self.start_trace(_AUTO_TRACE_NAME, metadata={_AUTO_TRACE_FLAG: True})

        parent = _active_span.get()

        span = Span(
            name=name,
            kind=kind,
            model=model,
            provider=provider,
            parent_span_id=parent.span_id if parent else None,
            metadata=metadata or {},
        )

        trace.add_span(span)

        # Remember the previously active span via the reset token so finish_span
        # can restore it. This keeps the parent/child tree correct for sibling
        # spans and for sequential calls within the same parent.
        span._token = _active_span.set(span)
        return span

    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK) -> None:
        """Finish a span, persist it, and restore the parent as active span."""
        span.finish(status)
        self._save_span_safe(span)
        self._restore_parent(span)
        self._rollup_auto_trace()

    def finish_span_with_error(self, span: Span, exc: Exception) -> None:
        """Finish a span in error state, persist it, and restore the parent."""
        span.finish_with_error(exc)
        self._save_span_safe(span)
        self._restore_parent(span)
        self._rollup_auto_trace()

    def _restore_parent(self, span: Span) -> None:
        """Restore the span that was active before ``span`` started.

        Resetting via the contextvar token (captured in ``start_span``) restores
        the *parent* span rather than clearing the context, so sibling spans and
        sequential calls within the same parent are tracked correctly.
        """
        token = span._token
        if token is not None:
            span._token = None
            _active_span.reset(token)

    def _rollup_auto_trace(self) -> None:
        """Keep an implicit "auto" trace's totals current as its spans finish.

        Explicit @trace runs are rolled up by finish_trace, so only auto-created
        traces are refreshed here — this gives `peekai list`/`stats`/UI correct
        totals even though an auto trace has no explicit end.
        """
        trace = _active_trace.get()
        if trace is not None and trace.metadata.get(_AUTO_TRACE_FLAG):
            trace.finish()
            self._save_trace_safe(trace)

    # ------------------------------------------------------------------
    # Guarded persistence — instrumentation must never break user code
    # ------------------------------------------------------------------

    def _save_span_safe(self, span: Span) -> None:
        try:
            self.storage.save_span(span)
        except Exception:
            logger.warning("peekai: failed to persist span %s", span.span_id, exc_info=True)

    def _save_trace_safe(self, trace: Trace) -> None:
        try:
            self.storage.save_trace(trace)
        except Exception:
            logger.warning("peekai: failed to persist trace %s", trace.trace_id, exc_info=True)

    # ------------------------------------------------------------------
    # Context accessors
    # ------------------------------------------------------------------

    @property
    def current_trace(self) -> Trace | None:
        return _active_trace.get()

    @property
    def current_span(self) -> Span | None:
        return _active_span.get()

    # ------------------------------------------------------------------
    # @trace() decorator
    # ------------------------------------------------------------------

    def trace(self, name: str | None = None) -> Callable[..., Any]:
        """
        Decorator that wraps a function in a top-level Trace.

        Usage:
            @tracer.trace("my_agent")
            def run():
                ...
        """
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            trace_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    t = self.start_trace(trace_name)
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_trace(t)
                        return result
                    except Exception as exc:
                        t.status = SpanStatus.ERROR
                        self.finish_trace(t)
                        raise exc
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    t = self.start_trace(trace_name)
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_trace(t)
                        return result
                    except Exception as exc:
                        t.status = SpanStatus.ERROR
                        self.finish_trace(t)
                        raise exc
                return sync_wrapper

        return decorator

    # ------------------------------------------------------------------
    # @agent() decorator  — Phase 5
    # ------------------------------------------------------------------

    def agent(self, name: str | None = None) -> Callable[..., Any]:
        """
        Decorator that wraps a sub-agent function in an AGENT span.

        Automatically propagates the parent span context so the sub-agent's
        LLM calls appear as children in the waterfall tree.

        Usage:
            @tracer.agent("researcher")
            def researcher_agent(task: str) -> str:
                # LLM calls here become children of the researcher span
                ...

            @tracer.agent()
            async def writer_agent(draft: str) -> str:
                ...
        """
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            agent_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # AGENT span — becomes the parent for every span created
                    # inside fn. finish_span restores the caller's span via the
                    # contextvar reset token, so siblings stay siblings.
                    agent_span = self.start_span(agent_name, kind=SpanKind.AGENT)
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_span(agent_span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(agent_span, exc)
                        raise
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    agent_span = self.start_span(agent_name, kind=SpanKind.AGENT)
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_span(agent_span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(agent_span, exc)
                        raise
                return sync_wrapper

        return decorator

    # ------------------------------------------------------------------
    # @tool() decorator
    # ------------------------------------------------------------------

    def tool(self, name: str | None = None) -> Callable[..., Any]:
        """
        Decorator that wraps a tool function in a TOOL span.

        Usage:
            @tracer.tool("search_web")
            def search(query: str) -> str:
                ...
        """
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            span_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    span = self.start_span(span_name, kind=SpanKind.TOOL)
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_span(span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(span, exc)
                        raise exc
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    span = self.start_span(span_name, kind=SpanKind.TOOL)
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_span(span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(span, exc)
                        raise exc
                return sync_wrapper

        return decorator
