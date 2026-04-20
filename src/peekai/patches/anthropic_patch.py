"""
Anthropic SDK monkey-patch.

Wraps `anthropic.resources.messages.Messages.create` (sync + async).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import SpanKind, SpanStatus

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

_patched = False


def patch(tracer: Tracer) -> None:
    global _patched
    if _patched:
        return

    try:
        from anthropic.resources.messages import AsyncMessages, Messages
    except ImportError:
        return  # anthropic not installed — skip silently

    _patch_sync(Messages, tracer)
    _patch_async(AsyncMessages, tracer)
    _patched = True


def unpatch() -> None:
    global _patched
    if not _patched:
        return
    try:
        from anthropic.resources.messages import AsyncMessages, Messages
        if hasattr(Messages, "_peekai_original_create"):
            Messages.create = Messages._peekai_original_create  # type: ignore[attr-defined]
            del Messages._peekai_original_create  # type: ignore[attr-defined]
        if hasattr(AsyncMessages, "_peekai_original_create"):
            AsyncMessages.create = AsyncMessages._peekai_original_create  # type: ignore[attr-defined]
            del AsyncMessages._peekai_original_create  # type: ignore[attr-defined]
    except ImportError:
        pass
    _patched = False


# ------------------------------------------------------------------
# Sync patch
# ------------------------------------------------------------------

def _patch_sync(Messages: Any, tracer: Tracer) -> None:
    original = Messages.create
    Messages._peekai_original_create = original  # type: ignore[attr-defined]

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: str = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        # Prepend system prompt as a synthetic message for display
        span.input = (
            [{"role": "system", "content": system}] + messages if system else messages
        )

        try:
            response = original(self, *args, **kwargs)
            _populate_span_from_response(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    Messages.create = patched_create  # type: ignore[method-assign]


# ------------------------------------------------------------------
# Async patch
# ------------------------------------------------------------------

def _patch_async(AsyncMessages: Any, tracer: Tracer) -> None:
    original = AsyncMessages.create
    AsyncMessages._peekai_original_create = original  # type: ignore[attr-defined]

    async def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: str = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        span.input = (
            [{"role": "system", "content": system}] + messages if system else messages
        )

        try:
            response = await original(self, *args, **kwargs)
            _populate_span_from_response(span, response, model)
            tracer.finish_span(span, SpanStatus.OK)
            return response
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

    AsyncMessages.create = patched_create  # type: ignore[method-assign]


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------

def _populate_span_from_response(span: Any, response: Any, model: str) -> None:
    try:
        usage = response.usage
        if usage:
            span.input_tokens = usage.input_tokens or 0
            span.output_tokens = usage.output_tokens or 0
            span.total_tokens = span.input_tokens + span.output_tokens
            span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)

        # Extract text from content blocks
        text_parts = [
            block.text
            for block in response.content
            if hasattr(block, "text")
        ]
        span.output = "\n".join(text_parts)

        # Tool use blocks
        tool_uses = [
            {
                "id": block.id,
                "function": block.name,
                "arguments": block.input,
            }
            for block in response.content
            if block.type == "tool_use"
        ]
        if tool_uses:
            span.tool_calls = tool_uses

        span.raw_response = {
            "id": response.id,
            "model": response.model,
            "stop_reason": response.stop_reason,
        }
    except Exception:
        pass
