"""
OpenAI SDK monkey-patch.

Wraps `openai.resources.chat.completions.Completions.create` (sync + async)
so every call is automatically captured as a Span. Streaming calls
(`stream=True`) are wrapped so output and usage are captured as the caller
consumes the stream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import SpanKind, SpanStatus
from peekai.patches._stream import OpenAIAccumulator, wrap_async, wrap_sync
from peekai.patches.registry import get_tracer, set_tracer

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

_patched = False


def patch(tracer: Tracer) -> None:
    set_tracer(tracer)  # always register the latest tracer (re-init safe)

    global _patched
    if _patched:
        return

    try:
        from openai.resources.chat.completions import AsyncCompletions, Completions
    except ImportError:
        return  # openai not installed — skip silently

    _patch_sync(Completions)
    _patch_async(AsyncCompletions)
    _patched = True


def unpatch() -> None:
    """Restore original methods (useful in tests)."""
    global _patched
    if not _patched:
        return
    try:
        from openai.resources.chat.completions import AsyncCompletions, Completions
    except ImportError:
        _patched = False
        return
    targets: list[Any] = [Completions, AsyncCompletions]
    for cls in targets:
        original = getattr(cls, "_peekai_original_create", None)
        if original is not None:
            cls.create = original
            delattr(cls, "_peekai_original_create")
    _patched = False


# ------------------------------------------------------------------
# Sync patch
# ------------------------------------------------------------------

def _patch_sync(Completions: Any) -> None:
    original = Completions.create
    Completions._peekai_original_create = original

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return original(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])

        span = tracer.start_span(
            name=f"openai/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="openai",
        )
        span.input = messages

        try:
            response = original(self, *args, **kwargs)
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

        if kwargs.get("stream"):
            # Finish now to restore the active-span context; the proxy updates
            # the span as the caller consumes the stream.
            tracer.finish_span(span, SpanStatus.OK)
            return wrap_sync(response, span, OpenAIAccumulator(), model, tracer)

        _populate_span_from_response(span, response, model)
        tracer.finish_span(span, SpanStatus.OK)
        return response

    Completions.create = patched_create


# ------------------------------------------------------------------
# Async patch
# ------------------------------------------------------------------

def _patch_async(AsyncCompletions: Any) -> None:
    original = AsyncCompletions.create
    AsyncCompletions._peekai_original_create = original

    async def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return await original(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])

        span = tracer.start_span(
            name=f"openai/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="openai",
        )
        span.input = messages

        try:
            response = await original(self, *args, **kwargs)
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

        if kwargs.get("stream"):
            tracer.finish_span(span, SpanStatus.OK)
            return wrap_async(response, span, OpenAIAccumulator(), model, tracer)

        _populate_span_from_response(span, response, model)
        tracer.finish_span(span, SpanStatus.OK)
        return response

    AsyncCompletions.create = patched_create


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _populate_span_from_response(span: Any, response: Any, model: str) -> None:
    """Extract tokens, cost, output, and tool calls from an OpenAI response."""
    try:
        usage = response.usage
        if usage:
            span.input_tokens = usage.prompt_tokens or 0
            span.output_tokens = usage.completion_tokens or 0
            span.total_tokens = usage.total_tokens or 0
            span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)

        choice = response.choices[0] if response.choices else None
        if choice:
            msg = choice.message
            span.output = msg.content or ""
            if msg.tool_calls:
                span.tool_calls = [
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in msg.tool_calls
                ]

        # Store a lightweight version of the raw response
        span.raw_response = {
            "id": response.id,
            "model": response.model,
            "finish_reason": choice.finish_reason if choice else None,
        }
    except Exception:
        pass  # never let instrumentation break user code
