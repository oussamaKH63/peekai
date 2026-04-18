"""peekai stats — show aggregate cost, token, and run totals."""

from __future__ import annotations

from rich.table import Table

from peekai.cli.console import console, get_storage


def stats() -> None:
    """Show total cost, tokens, and run counts across all traces."""
    storage = get_storage()
    data = storage.get_stats()
    traces = storage.list_traces(limit=200)
    storage.close()

    if data["total_runs"] == 0:
        console.print("[dim]No completed traces yet.[/dim]")
        return

    # Per-model breakdown from spans
    model_stats: dict[str, dict[str, float | int]] = {}
    for t in traces:
        for span in t.spans:
            if not span.model:
                continue
            if span.model not in model_stats:
                model_stats[span.model] = {"tokens": 0, "cost": 0.0, "calls": 0}
            model_stats[span.model]["tokens"] += span.total_tokens  # type: ignore[operator]
            model_stats[span.model]["cost"] += span.cost_usd  # type: ignore[operator]
            model_stats[span.model]["calls"] += 1  # type: ignore[operator]

    # ── Summary panel ─────────────────────────────────────────────
    summary = Table.grid(padding=(0, 3))
    summary.add_column(style="label")
    summary.add_column()
    summary.add_row("Total runs", str(data["total_runs"]))
    summary.add_row("Total tokens", f"{data['total_tokens']:,}")
    summary.add_row("Total cost", f"[cost]${data['total_cost_usd']:.6f} USD[/cost]")

    console.print()
    console.print(summary)

    # ── Per-model breakdown ────────────────────────────────────────
    if model_stats:
        console.print("\n[bold]By model[/bold]\n")
        table = Table(
            show_header=True,
            header_style="bold",
            border_style="dim",
        )
        table.add_column("Model", style="model")
        table.add_column("Calls", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Cost (USD)", justify="right", style="cost")

        for model, s in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True):
            table.add_row(
                model,
                str(s["calls"]),
                f"{s['tokens']:,}",
                f"${s['cost']:.6f}",
            )

        console.print(table)

    console.print()
