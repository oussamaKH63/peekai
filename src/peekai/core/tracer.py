"""
Tracer — manages the active Trace and Span lifecycle.

Uses contextvars so it is safe in async / multi-threaded code.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage

# Context variables — one active trace and one active span per async context
_active_trace: ContextVar[Trace | None] = ContextVar("_active_trace", default=None)
_active_span: ContextVar[Span | None] = ContextVar("_active_span", default=None)


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
        self.storage.save_trace(trace)
        return trace

    def finish_trace(self, trace: Trace | None = None) -> Trace | None:
        """Finish the given trace (or the active one) and persist it."""
        t = trace or _active_trace.get()
        if t is None:
            return None
        t.finish()
        self.storage.save_trace(t)
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
        parent = _active_span.get()

        span = Span(
            name=name,
            kind=kind,
            model=model,
            provider=provider,
            parent_span_id=parent.span_id if parent else None,
            metadata=metadata or {},
        )

        if trace is not None:
            trace.add_span(span)

        _active_span.set(span)
        return span

    def finish_span(self, span: Span, status: SpanStatus = SpanStatus.OK) -> None:
        """Finish a span and persist it."""
        span.finish(status)
        self.storage.save_span(span)
        _active_span.set(None)

    def finish_span_with_error(self, span: Span, exc: Exception) -> None:
        """Finish a span in error state and persist it."""
        span.finish_with_error(exc)
        self.storage.save_span(span)
        _active_span.set(None)

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
        import asyncio

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
        import asyncio

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            agent_name = name or fn.__name__

            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    # Create an AGENT span — becomes parent for all spans inside
                    agent_span = self.start_span(agent_name, kind=SpanKind.AGENT)
                    # Save the caller's span so we can restore it after
                    previous_span = _active_span.get()
                    _active_span.set(agent_span)
                    try:
                        result = await fn(*args, **kwargs)
                        self.finish_span(agent_span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(agent_span, exc)
                        raise exc
                    finally:
                        # Restore caller's span context
                        _active_span.set(previous_span)
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    agent_span = self.start_span(agent_name, kind=SpanKind.AGENT)
                    previous_span = _active_span.get()
                    _active_span.set(agent_span)
                    try:
                        result = fn(*args, **kwargs)
                        self.finish_span(agent_span)
                        return result
                    except Exception as exc:
                        self.finish_span_with_error(agent_span, exc)
                        raise exc
                    finally:
                        _active_span.set(previous_span)
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
        import asyncio

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
