"""
OpenAI SDK monkey-patch.

Wraps `openai.resources.chat.completions.Completions.create` (sync + async)
so every call is automatically captured as a Span.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import SpanKind, SpanStatus

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

_patched = False


def patch(tracer: "Tracer") -> None:
    global _patched
    if _patched:
        return

    try:
        import openai
        from openai.resources.chat.completions import Completions, AsyncCompletions
    except ImportError:
        return  # openai not installed — skip silently

    _patch_sync(Completions, tracer)
    _patch_async(AsyncCompletions, tracer)
    _patched = True


def unpatch() -> None:
    """Restore original methods (useful in tests)."""
    global _patched
    if not _patched:
        return
    try:
        from openai.resources.chat.completions import Completions, AsyncCompletions
        if hasattr(Completions, "_peekai_original_create"):
            Completions.create = Completions._peekai_original_create  # type: ignore[attr-defined]
            del Completions._peekai_original_create  # type: ignore[attr-defined]
        if hasattr(AsyncCompletions, "_peekai_original_create"):
            AsyncCompletions.create = AsyncCompletions._peekai_original_create  # type: ignore[attr-defined]
            del AsyncCompletions._peekai_original_create  # type: ignore[attr-defined]
    except ImportError:
        pass
    _patched = False


# ------------------------------------------------------------------
# Sync patch
# ------------------------------------------------------------------

def _patch_sync(Completions: Any, tracer: "Tracer") -> None:
    original = Completions.create
    Completions._peekai_original_create = original  # type: ignore[attr-defined]

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
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
            _populate_span_from_response(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    Completions.create = patched_create  # type: ignore[method-assign]


# ------------------------------------------------------------------
# Async patch
# ------------------------------------------------------------------

def _patch_async(AsyncCompletions: Any, tracer: "Tracer") -> None:
    original = AsyncCompletions.create
    AsyncCompletions._peekai_original_create = original  # type: ignore[attr-defined]

    async def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
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
            _populate_span_from_response(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    AsyncCompletions.create = patched_create  # type: ignore[method-assign]


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
