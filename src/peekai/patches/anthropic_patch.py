"""
Anthropic SDK monkey-patch.

Wraps `anthropic.resources.messages.Messages.create` (sync + async). Streaming
calls made via `create(stream=True)` are wrapped so text and usage are captured
as the caller consumes the stream. (The `client.messages.stream()` helper is a
separate API and is not patched.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from peekai.core.costs import calculate_cost
from peekai.core.models import SpanKind, SpanStatus
from peekai.patches._stream import AnthropicAccumulator, AsyncTracedMessageStreamManager, TracedMessageStreamManager, wrap_async, wrap_sync
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
        from anthropic.resources.messages import AsyncMessages, Messages
    except ImportError:
        return  # anthropic not installed — skip silently

    _patch_sync(Messages)
    _patch_async(AsyncMessages)
    _patched = True


def unpatch() -> None:
    global _patched
    if not _patched:
        return
    try:
        from anthropic.resources.messages import AsyncMessages, Messages
    except ImportError:
        _patched = False
        return
    targets: list[Any] = [Messages, AsyncMessages]
    for cls in targets:
        for method in ("create", "stream"):
            original = getattr(cls, f"_peekai_original_{method}", None)
            if original is not None:
                setattr(cls, method, original)
                delattr(cls, f"_peekai_original_{method}")
    _patched = False


def _build_input(messages: list[dict[str, Any]], system: Any) -> list[dict[str, Any]]:
    """Prepend the system prompt as a synthetic message for display."""
    if system:
        return [{"role": "system", "content": system}] + messages
    return messages


# ------------------------------------------------------------------
# Sync patch
# ------------------------------------------------------------------

def _patch_sync(Messages: Any) -> None:
    original = Messages.create
    Messages._peekai_original_create = original

    def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return original(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: Any = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        span.input = _build_input(messages, system)

        try:
            response = original(self, *args, **kwargs)
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

        if kwargs.get("stream"):
            tracer.finish_span(span, SpanStatus.OK)
            return wrap_sync(response, span, AnthropicAccumulator(), model, tracer)

        _populate_span_from_response(span, response, model)
        tracer.finish_span(span, SpanStatus.OK)
        return response

    Messages.create = patched_create

    original_stream = Messages.stream
    Messages._peekai_original_stream = original_stream

    def patched_stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return original_stream(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: Any = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        span.input = _build_input(messages, system)
        tracer.finish_span(span, SpanStatus.OK)

        manager = original_stream(self, *args, **kwargs)
        return TracedMessageStreamManager(manager, span, model, tracer)

    Messages.stream = patched_stream


# ------------------------------------------------------------------
# Async patch
# ------------------------------------------------------------------

def _patch_async(AsyncMessages: Any) -> None:
    original = AsyncMessages.create
    AsyncMessages._peekai_original_create = original

    async def patched_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return await original(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: Any = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        span.input = _build_input(messages, system)

        try:
            response = await original(self, *args, **kwargs)
        except Exception as exc:
            tracer.finish_span_with_error(span, exc)
            raise

        if kwargs.get("stream"):
            tracer.finish_span(span, SpanStatus.OK)
            return wrap_async(response, span, AnthropicAccumulator(), model, tracer)

        _populate_span_from_response(span, response, model)
        tracer.finish_span(span, SpanStatus.OK)
        return response

    AsyncMessages.create = patched_create

    original_stream = AsyncMessages.stream
    AsyncMessages._peekai_original_stream = original_stream

    def patched_stream(self: Any, *args: Any, **kwargs: Any) -> Any:
        tracer = get_tracer()
        if tracer is None:
            return original_stream(self, *args, **kwargs)

        model: str = kwargs.get("model", "")
        messages: list[dict[str, Any]] = kwargs.get("messages", [])
        system: Any = kwargs.get("system", "")

        span = tracer.start_span(
            name=f"anthropic/{model}",
            kind=SpanKind.LLM,
            model=model,
            provider="anthropic",
        )
        span.input = _build_input(messages, system)
        tracer.finish_span(span, SpanStatus.OK)

        manager = original_stream(self, *args, **kwargs)
        return AsyncTracedMessageStreamManager(manager, span, model, tracer)

    AsyncMessages.stream = patched_stream


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
