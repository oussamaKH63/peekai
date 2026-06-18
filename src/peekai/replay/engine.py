"""
Trace Replay Engine — Phase 4

Re-runs every LLM span in a trace using the stored prompt,
optionally swapping the model or injecting modified tool responses.

How it works:
  1. Load the original trace from storage
  2. For each LLM span (in order):
     - Use the stored input messages as the prompt
     - Call the LLM with the (optionally swapped) model
     - Record a new span with the new response
  3. Save the replay as a new Trace with metadata linking it to the original
  4. Return both traces so callers can compare them
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from peekai.core.costs import calculate_cost
from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage


@dataclass
class ReplayResult:
    """Holds the original and replayed traces side by side."""
    original: Trace
    replayed: Trace
    span_pairs: list[tuple[Span, Span | None]] = field(default_factory=list)
    # span_pairs[i] = (original_span, replayed_span | None)
    # replayed_span is None for tool/non-LLM spans that were not re-executed


class ReplayEngine:
    """
    Replays a stored trace by re-sending each LLM span's input to the API.

    Args:
        storage:        Storage instance to read/write traces.
        model_override: If set, use this model instead of the original.
        tool_overrides: Dict mapping tool name → fake return value.
        api_key:        API key (defaults to OPENAI_API_KEY env var).
        base_url:       Custom base URL for OpenAI-compatible endpoints.
    """

    def __init__(
        self,
        storage: Storage | None = None,
        model_override: str | None = None,
        tool_overrides: dict[str, Any] | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.storage = storage or Storage()
        self.model_override = model_override
        self.tool_overrides = tool_overrides or {}
        self.api_key = api_key
        self.base_url = base_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def replay(self, trace_id: str) -> ReplayResult:
        """
        Replay a trace by its ID (full or short prefix).

        Returns a ReplayResult with both the original and new trace.
        Raises ValueError if the trace is not found.
        """
        original = self._resolve_trace(trace_id)
        if original is None:
            raise ValueError(f"Trace '{trace_id}' not found.")

        llm_spans = [s for s in original.spans if s.kind == SpanKind.LLM]
        if not llm_spans:
            raise ValueError(f"Trace '{trace_id}' has no LLM spans to replay.")

        # Build the replayed trace
        replayed = Trace(
            name=f"{original.name} [replay]",
            metadata={
                "original_trace_id": original.trace_id,
                "model_override": self.model_override or "",
                "tool_overrides": list(self.tool_overrides.keys()),
            },
        )
        self.storage.save_trace(replayed)

        span_pairs: list[tuple[Span, Span | None]] = []

        for orig_span in original.spans:
            if orig_span.kind != SpanKind.LLM:
                # Non-LLM spans (tools, agents) — record as-is, no re-execution
                span_pairs.append((orig_span, None))
                continue

            replayed_span = self._replay_llm_span(orig_span, replayed.trace_id)
            replayed.add_span(replayed_span)  # keep in-memory list for rollup
            span_pairs.append((orig_span, replayed_span))

        replayed.finish()
        self.storage.save_trace(replayed)

        result = ReplayResult(
            original=original,
            replayed=replayed,
            span_pairs=span_pairs,
        )
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_trace(self, trace_id: str) -> Trace | None:
        """Support both full UUIDs and short 8-char prefixes."""
        if len(trace_id) >= 36:
            return self.storage.get_trace(trace_id)
        # Short ID — scan recent traces
        candidates = self.storage.list_traces(limit=500)
        for t in candidates:
            if t.trace_id.startswith(trace_id):
                return self.storage.get_trace(t.trace_id)
        return None

    def _apply_tool_overrides(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Rewrite tool/function result messages whose name matches an override.

        Best-effort: matches messages with role ``tool``/``function`` and a
        ``name`` equal to an override key, replacing their ``content`` with the
        supplied value. Messages without a ``name`` cannot be matched.
        """
        if not self.tool_overrides:
            return messages

        patched: list[dict[str, Any]] = []
        for msg in messages:
            name = msg.get("name")
            if msg.get("role") in ("tool", "function") and name in self.tool_overrides:
                new_msg = dict(msg)
                new_msg["content"] = self.tool_overrides[name]
                patched.append(new_msg)
            else:
                patched.append(msg)
        return patched

    def _replay_llm_span(self, orig: Span, new_trace_id: str) -> Span:
        """Re-send the original span's messages to the LLM and record a new span."""
        model = self.model_override or orig.model
        provider = self._infer_provider(model, orig.provider)

        new_span = Span(
            trace_id=new_trace_id,
            name=f"{orig.name} [replay]",
            kind=SpanKind.LLM,
            model=model,
            provider=provider,
            input=self._apply_tool_overrides(orig.input),
            parent_span_id=orig.parent_span_id,
            metadata={"original_span_id": orig.span_id},
        )

        try:
            if provider == "anthropic":
                self._call_anthropic(new_span, model)
            else:
                # Default: OpenAI-compatible (covers openai + litellm)
                self._call_openai(new_span, model)
        except Exception as exc:
            new_span.finish_with_error(exc)

        self.storage.save_span(new_span)
        return new_span

    def _call_openai(self, span: Span, model: str) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package not installed. Run: uv add openai")

        kwargs: dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url

        client = OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=span.input,  # type: ignore[arg-type]
        )
        usage = response.usage
        if usage:
            span.input_tokens = usage.prompt_tokens or 0
            span.output_tokens = usage.completion_tokens or 0
            span.total_tokens = usage.total_tokens or 0
            span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)

        choice = response.choices[0] if response.choices else None
        if choice:
            span.output = choice.message.content or ""
            tool_calls: Any = choice.message.tool_calls
            if tool_calls:
                span.tool_calls = [
                    {"id": tc.id, "function": tc.function.name, "arguments": tc.function.arguments}
                    for tc in tool_calls
                ]
        span.raw_response = {
            "id": response.id,
            "model": response.model,
            "finish_reason": choice.finish_reason if choice else None,
        }
        span.finish(SpanStatus.OK)

    def _call_anthropic(self, span: Span, model: str) -> None:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package not installed. Run: uv add anthropic")

        client = anthropic.Anthropic()
        # Separate system message from the rest
        messages = [m for m in span.input if m.get("role") != "system"]
        system = next((m.get("content", "") for m in span.input if m.get("role") == "system"), "")

        kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": 1024}
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        usage = response.usage
        if usage:
            span.input_tokens = usage.input_tokens or 0
            span.output_tokens = usage.output_tokens or 0
            span.total_tokens = span.input_tokens + span.output_tokens
            span.cost_usd = calculate_cost(model, span.input_tokens, span.output_tokens)

        span.output = "\n".join(
            block.text for block in response.content if hasattr(block, "text")
        )
        span.raw_response = {"id": response.id, "model": response.model, "stop_reason": response.stop_reason}
        span.finish(SpanStatus.OK)

    def _infer_provider(self, model: str, original_provider: str) -> str:
        """Infer provider from model name when overriding."""
        if not self.model_override:
            return original_provider
        m = model.lower()
        if m.startswith("claude"):
            return "anthropic"
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3"):
            return "openai"
        return "litellm"
