"""peekai view <trace-id> — pretty-print a full trace with all spans."""

from __future__ import annotations

import json

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from peekai.cli.console import console, get_storage
from peekai.core.models import SpanStatus

_STATUS_STYLE = {
    SpanStatus.OK: ("ok", "✓"),
    SpanStatus.ERROR: ("error", "✗"),
    SpanStatus.PENDING: ("pending", "⏳"),
}


def view(
    trace_id: str = typer.Argument(..., help="Trace ID (full or first 8 chars)"),
) -> None:
    """Pretty-print a trace and all its spans."""
    storage = get_storage()

    # Support short IDs — find the first match
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

    # ── Trace header ──────────────────────────────────────────────
    style, icon = _STATUS_STYLE.get(trace.status, ("dim", "?"))
    duration = f"{trace.duration_ms:.0f}ms" if trace.duration_ms is not None else "running"
    started = trace.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()
    header.add_row("[label]Trace ID[/label]", trace.trace_id)
    header.add_row("[label]Name[/label]", trace.name)
    header.add_row("[label]Status[/label]", f"[{style}]{icon} {trace.status.value}[/{style}]")
    header.add_row("[label]Started[/label]", started)
    header.add_row("[label]Duration[/label]", duration)
    header.add_row("[label]Tokens[/label]", f"{trace.total_tokens:,} ({trace.total_input_tokens:,} in / {trace.total_output_tokens:,} out)")
    header.add_row("[label]Cost[/label]", f"[cost]${trace.total_cost_usd:.6f}[/cost]")

    console.print()
    console.print(Panel(header, title="[bold]Trace[/bold]", border_style="dim"))

    if not trace.spans:
        console.print("[dim]  No spans recorded.[/dim]\n")
        return

    # ── Spans waterfall ───────────────────────────────────────────
    console.print(f"\n[bold]Spans[/bold] ({len(trace.spans)})\n")

    for i, span in enumerate(trace.spans):
        s_style, s_icon = _STATUS_STYLE.get(span.status, ("dim", "?"))
        s_duration = f"{span.duration_ms:.0f}ms" if span.duration_ms is not None else "—"
        indent = "  " if span.parent_span_id else ""
        connector = "└─" if span.parent_span_id else f"{'─' * 2}"

        # Span title line
        title_text = Text()
        title_text.append(f"{indent}{connector} ", style="dim")
        title_text.append(f"[{s_style}]{s_icon}[/{s_style}] ")
        title_text.append(span.name, style="bold")
        title_text.append(f"  {s_duration}", style="dim")
        if span.model:
            title_text.append(f"  [{span.model}]", style="model")
        if span.total_tokens:
            title_text.append(f"  {span.total_tokens:,} tokens", style="dim")
        if span.cost_usd:
            title_text.append(f"  ${span.cost_usd:.6f}", style="cost")

        console.print(title_text)

        # Error
        if span.error:
            console.print(f"{indent}   [error]{span.error_type}: {span.error}[/error]")

        # Input messages
        if span.input:
            console.print(f"{indent}   [dim]── input ──[/dim]")
            for msg in span.input:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, str):
                    preview = content[:200] + ("…" if len(content) > 200 else "")
                    console.print(f"{indent}   [dim]{role}:[/dim] {preview}")

        # Output
        if span.output:
            preview = span.output[:300] + ("…" if len(span.output) > 300 else "")
            console.print(f"{indent}   [dim]── output ──[/dim]")
            console.print(f"{indent}   {preview}")

        # Tool calls
        if span.tool_calls:
            console.print(f"{indent}   [dim]── tool calls ──[/dim]")
            for tc in span.tool_calls:
                console.print(f"{indent}   [model]{tc.get('function', '?')}[/model]  id={tc.get('id', '')}")
                args = tc.get("arguments", "")
                if args:
                    try:
                        parsed = json.loads(args) if isinstance(args, str) else args
                        syntax = Syntax(
                            json.dumps(parsed, indent=2),
                            "json",
                            theme="monokai",
                            word_wrap=True,
                        )
                        console.print(syntax)
                    except Exception:
                        console.print(f"{indent}   {args}")

        if i < len(trace.spans) - 1:
            console.print()

    console.print()
