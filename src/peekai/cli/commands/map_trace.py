"""
peekai map <trace-id> — ASCII agent flow tree in the terminal.

Example output:

  trace: multi_agent_run  [ok]  4.2s  173 tokens  $0.000140

  ── orchestrator_agent  [agent]  2.1s
     ├── openai/gpt-4o  [llm]  ✓  1.2s  45 tokens  $0.000045
     ├── researcher_agent  [agent]  0.8s
     │   ├── openai/gpt-4o  [llm]  ✓  0.4s  30 tokens  $0.000030
     │   └── search_web  [tool]  ✓  0.1s
     └── writer_agent  [agent]  0.5s
         └── openai/gpt-4o  [llm]  ✓  0.4s  28 tokens  $0.000028
"""

from __future__ import annotations

import typer
from rich.text import Text

from peekai.cli.console import console, get_storage
from peekai.core.models import Span, SpanKind, SpanStatus

_KIND_ICON = {
    SpanKind.LLM:   "🤖",
    SpanKind.TOOL:  "🔧",
    SpanKind.AGENT: "🧠",
    SpanKind.CHAIN: "🔗",
}

_STATUS_COLOR = {
    SpanStatus.OK:      "ok",
    SpanStatus.ERROR:   "error",
    SpanStatus.PENDING: "pending",
}


def map_trace(
    trace_id: str = typer.Argument(..., help="Trace ID (full or first 8 chars)"),
) -> None:
    """Print an ASCII agent flow tree for a trace."""
    storage = get_storage()

    if len(trace_id) < 36:
        all_traces = storage.list_traces(limit=200)
        matches = [t for t in all_traces if t.trace_id.startswith(trace_id)]
        if not matches:
            console.print(f"[error]No trace found matching '{trace_id}'[/error]")
            storage.close()
            raise typer.Exit(1)
        trace = storage.get_trace(matches[0].trace_id)
    else:
        trace = storage.get_trace(trace_id)

    storage.close()

    if trace is None:
        console.print(f"[error]Trace '{trace_id}' not found.[/error]")
        raise typer.Exit(1)

    if not trace.spans:
        console.print("[dim]No spans in this trace.[/dim]")
        return

    # ── Trace header ──────────────────────────────────────────────
    status_color = _STATUS_COLOR.get(trace.status, "dim")
    duration = f"{trace.duration_ms / 1000:.2f}s" if trace.duration_ms else "—"
    console.print()
    console.print(
        f"  [bold]trace:[/bold] [label]{trace.name}[/label]"
        f"  [{status_color}]{trace.status.value}[/{status_color}]"
        f"  [dim]{duration}  {trace.total_tokens:,} tokens  ${trace.total_cost_usd:.6f}[/dim]"
    )
    console.print()

    # ── Build parent→children map ─────────────────────────────────
    children: dict[str | None, list[Span]] = {}
    for span in trace.spans:
        parent_id = span.parent_span_id
        children.setdefault(parent_id, []).append(span)

    # ── Recursive tree printer ────────────────────────────────────
    def print_tree(span_id: str | None, prefix: str = "  ") -> None:
        kids = children.get(span_id, [])
        for i, span in enumerate(kids):
            last = i == len(kids) - 1
            connector = "└──" if last else "├──"
            # Prefix for this span's children
            child_prefix = prefix + ("    " if last else "│   ")

            icon = _KIND_ICON.get(span.kind, "•")
            dur = f"{span.duration_ms / 1000:.2f}s" if span.duration_ms else "—"

            line = Text()
            line.append(f"{prefix}{connector} ", style="dim")
            line.append(f"{icon} ")
            line.append(span.name, style="bold")
            line.append(f"  [{span.kind.value}]", style="dim")
            line.append("  ")
            if span.status == SpanStatus.OK:
                line.append(f"✓ {span.status.value}", style="ok")
            else:
                line.append(f"✗ {span.status.value}", style=_STATUS_COLOR.get(span.status, "dim"))
            line.append(f"  {dur}", style="dim")
            if span.total_tokens:
                line.append(f"  {span.total_tokens:,} tok", style="dim")
            if span.cost_usd:
                line.append(f"  ${span.cost_usd:.6f}", style="cost")
            if span.model:
                line.append(f"  {span.model}", style="model")
            if span.error:
                line.append(f"  ✗ {span.error_type}", style="error")

            console.print(line)

            # Recurse into children using the child prefix
            print_tree(span.span_id, child_prefix)

    # Start from root spans (no parent)
    print_tree(None)
    console.print()
