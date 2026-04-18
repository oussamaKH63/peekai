"""peekai list — show the last N traces."""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from peekai.cli.console import console, get_storage
from peekai.core.models import SpanStatus

_STATUS_STYLE = {
    SpanStatus.OK: "[ok]✓ ok[/ok]",
    SpanStatus.ERROR: "[error]✗ error[/error]",
    SpanStatus.PENDING: "[pending]⏳ pending[/pending]",
}


def list_traces(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of traces to show")] = 10,
) -> None:
    """Show the most recent traces."""
    storage = get_storage()
    traces = storage.list_traces(limit=limit)
    storage.close()

    if not traces:
        console.print("[dim]No traces found. Run an agent with peekai.init() first.[/dim]")
        raise typer.Exit()

    table = Table(
        show_header=True,
        header_style="bold",
        border_style="dim",
        show_lines=False,
    )
    table.add_column("Trace ID", style="dim", width=12)
    table.add_column("Name", style="label")
    table.add_column("Status", justify="center")
    table.add_column("Spans", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost (USD)", justify="right", style="cost")
    table.add_column("Duration", justify="right")
    table.add_column("Started", style="dim")

    for t in traces:
        short_id = t.trace_id[:8]
        status_str = _STATUS_STYLE.get(t.status, t.status.value)
        duration = f"{t.duration_ms:.0f}ms" if t.duration_ms is not None else "—"
        started = t.started_at.strftime("%Y-%m-%d %H:%M:%S")
        cost = f"${t.total_cost_usd:.6f}" if t.total_cost_usd else "—"
        span_count = len(t.spans) if t.spans else "—"

        table.add_row(
            short_id,
            t.name,
            status_str,
            str(span_count),
            str(t.total_tokens) if t.total_tokens else "—",
            cost,
            duration,
            started,
        )

    console.print()
    console.print(table)
    console.print(f"\n[dim]Showing {len(traces)} trace(s). Use --limit to see more.[/dim]\n")
