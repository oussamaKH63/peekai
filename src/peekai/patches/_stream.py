"""
Streaming-response capture for the SDK patches.

When a user calls an LLM with ``stream=True`` the SDK returns an iterator/stream
rather than a complete response, so tokens and output can only be observed as the
caller consumes it. We wrap the stream in a transparent proxy that:

  * delegates every attribute / context-manager call to the real stream, so user
    code keeps working (``for chunk in stream``, ``with stream as s``, ``.close()``);
  * taps each chunk to accumulate output text, tool calls, and usage;
  * finalizes and re-persists the span once the stream is exhausted or closed.

The owning span is finished (and the active-span context restored) at call time —
the proxy only updates the already-saved record, so streaming never interferes
with parent/child span tracking.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import Span, SpanStatus

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

Finalizer = Callable[[Exception | None], None]


class OpenAIAccumulator:
    """Accumulates content / tool calls / usage from OpenAI-style chunks."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._usage: Any = None
        self._tool_calls: dict[int, dict[str, str]] = {}

    def add(self, chunk: Any) -> None:
        choices = getattr(chunk, "choices", None) or []
        if choices:
            delta = getattr(choices[0], "delta", None)
            if delta is not None:
                content = getattr(delta, "content", None)
                if content:
                    self._parts.append(content)
                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = getattr(tc, "index", 0) or 0
                    slot = self._tool_calls.setdefault(
                        idx, {"id": "", "function": "", "arguments": ""}
                    )
                    if getattr(tc, "id", None):
                        slot["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["function"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["arguments"] += fn.arguments
        usage = getattr(chunk, "usage", None)
        if usage:
            self._usage = usage

    def apply(self, span: Span, model: str) -> None:
        span.output = "".join(self._parts)
        if self._usage is not None:
            span.input_tokens = getattr(self._usage, "prompt_tokens", 0) or 0
            span.output_tokens = getattr(self._usage, "completion_tokens", 0) or 0
            span.total_tokens = getattr(self._usage, "total_tokens", 0) or (
                span.input_tokens + span.output_tokens
            )
            span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)
        if self._tool_calls:
            span.tool_calls = [self._tool_calls[i] for i in sorted(self._tool_calls)]


class AnthropicAccumulator:
    """Accumulates text + usage from Anthropic streaming events."""

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._input_tokens = 0
        self._output_tokens = 0

    def add(self, event: Any) -> None:
        etype = getattr(event, "type", "")
        if etype == "content_block_delta":
            delta = getattr(event, "delta", None)
            text = getattr(delta, "text", None) if delta is not None else None
            if text:
                self._parts.append(text)
        elif etype == "message_start":
            message = getattr(event, "message", None)
            usage = getattr(message, "usage", None) if message is not None else None
            if usage is not None:
                self._input_tokens = getattr(usage, "input_tokens", 0) or 0
        elif etype == "message_delta":
            usage = getattr(event, "usage", None)
            if usage is not None:
                self._output_tokens = getattr(usage, "output_tokens", 0) or 0

    def apply(self, span: Span, model: str) -> None:
        span.output = "".join(self._parts)
        span.input_tokens = self._input_tokens
        span.output_tokens = self._output_tokens
        span.total_tokens = self._input_tokens + self._output_tokens
        span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)


def _make_finalizer(
    span: Span, accumulator: Any, model: str, tracer: Tracer
) -> Finalizer:
    def finalize(error: Exception | None) -> None:
        try:
            accumulator.apply(span, model)
        except Exception:
            pass
        span.metadata["streaming"] = True
        span.ended_at = datetime.now(timezone.utc)
        if error is not None:
            span.status = SpanStatus.ERROR
            span.error = str(error)
            span.error_type = type(error).__name__
        tracer._save_span_safe(span)

    return finalize


class _TracedStream:
    """Transparent proxy over a synchronous SDK stream."""

    def __init__(self, stream: Any, accumulator: Any, finalize: Finalizer) -> None:
        self._stream = stream
        self._acc = accumulator
        self._finalize = finalize
        self._done = False

    def _finish(self, error: Exception | None = None) -> None:
        if not self._done:
            self._done = True
            self._finalize(error)

    def __iter__(self) -> Iterator[Any]:
        error: Exception | None = None
        try:
            for chunk in self._stream:
                try:
                    self._acc.add(chunk)
                except Exception:
                    pass
                yield chunk
        except Exception as exc:
            error = exc
            raise
        finally:
            self._finish(error)

    def __enter__(self) -> _TracedStream:
        enter = getattr(self._stream, "__enter__", None)
        if enter is not None:
            enter()
        return self

    def __exit__(self, *exc: Any) -> Any:
        self._finish(exc[1] if len(exc) > 1 else None)
        exit_ = getattr(self._stream, "__exit__", None)
        if exit_ is not None:
            return exit_(*exc)
        return False

    def close(self) -> None:
        self._finish()
        close = getattr(self._stream, "close", None)
        if close is not None:
            close()

    def __getattr__(self, name: str) -> Any:
        stream = self.__dict__.get("_stream")
        if stream is None:
            raise AttributeError(name)
        return getattr(stream, name)


class _AsyncTracedStream:
    """Transparent proxy over an asynchronous SDK stream."""

    def __init__(self, stream: Any, accumulator: Any, finalize: Finalizer) -> None:
        self._stream = stream
        self._acc = accumulator
        self._finalize = finalize
        self._done = False

    def _finish(self, error: Exception | None = None) -> None:
        if not self._done:
            self._done = True
            self._finalize(error)

    async def __aiter__(self) -> AsyncIterator[Any]:
        error: Exception | None = None
        try:
            async for chunk in self._stream:
                try:
                    self._acc.add(chunk)
                except Exception:
                    pass
                yield chunk
        except Exception as exc:
            error = exc
            raise
        finally:
            self._finish(error)

    async def __aenter__(self) -> _AsyncTracedStream:
        aenter = getattr(self._stream, "__aenter__", None)
        if aenter is not None:
            await aenter()
        return self

    async def __aexit__(self, *exc: Any) -> Any:
        self._finish(exc[1] if len(exc) > 1 else None)
        aexit = getattr(self._stream, "__aexit__", None)
        if aexit is not None:
            return await aexit(*exc)
        return False

    async def aclose(self) -> None:
        self._finish()
        aclose = getattr(self._stream, "aclose", None)
        if aclose is not None:
            await aclose()

    def __getattr__(self, name: str) -> Any:
        stream = self.__dict__.get("_stream")
        if stream is None:
            raise AttributeError(name)
        return getattr(stream, name)


def wrap_sync(
    stream: Any, span: Span, accumulator: Any, model: str, tracer: Tracer
) -> _TracedStream:
    """Wrap a sync stream so the span is finalized when it is consumed."""
    finalize = _make_finalizer(span, accumulator, model, tracer)
    return _TracedStream(stream, accumulator, finalize)


def wrap_async(
    stream: Any, span: Span, accumulator: Any, model: str, tracer: Tracer
) -> _AsyncTracedStream:
    """Wrap an async stream so the span is finalized when it is consumed."""
    finalize = _make_finalizer(span, accumulator, model, tracer)
    return _AsyncTracedStream(stream, accumulator, finalize)
