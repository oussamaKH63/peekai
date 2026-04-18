"""
LiteLLM monkey-patch.

Wraps `litellm.completion` and `litellm.acompletion` (the top-level functions).
LiteLLM uses an OpenAI-compatible response format, so we reuse the same
response parser as the OpenAI patch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import SpanKind, SpanStatus

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

_patched = False
_original_completion: Any = None
_original_acompletion: Any = None


def patch(tracer: "Tracer") -> None:
    global _patched, _original_completion, _original_acompletion
    if _patched:
        return

    try:
        import litellm
    except ImportError:
        return  # litellm not installed — skip silently

    _original_completion = litellm.completion
    _original_acompletion = litellm.acompletion

    def patched_completion(*args: Any, **kwargs: Any) -> Any:
        model: str = kwargs.get("model", args[0] if args else "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])

        span = tracer.start_span(
            name=f"litellm/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="litellm",
        )
        span.input = messages

        try:
            response = _original_completion(*args, **kwargs)
            _populate_span(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    async def patched_acompletion(*args: Any, **kwargs: Any) -> Any:
        model: str = kwargs.get("model", args[0] if args else "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])

        span = tracer.start_span(
            name=f"litellm/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="litellm",
        )
        span.input = messages

        try:
            response = await _original_acompletion(*args, **kwargs)
            _populate_span(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    litellm.completion = patched_completion
    litellm.acompletion = patched_acompletion
    _patched = True


def unpatch() -> None:
    global _patched, _original_completion, _original_acompletion
    if not _patched:
        return
    try:
        import litellm
        if _original_completion:
            litellm.completion = _original_completion
        if _original_acompletion:
            litellm.acompletion = _original_acompletion
    except ImportError:
        pass
    _patched = False


def _populate_span(span: Any, response: Any, model: str) -> None:
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
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                span.tool_calls = [
                    {
                        "id": tc.id,
                        "function": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                    for tc in msg.tool_calls
                ]

        span.raw_response = {
            "id": getattr(response, "id", ""),
            "model": getattr(response, "model", model),
            "finish_reason": choice.finish_reason if choice else None,
        }
    except Exception:
        pass
