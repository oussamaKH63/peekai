"""
peekai replay <trace-id> — re-run a past trace, optionally with a different model.

Examples:
    peekai replay 976c5a32
    peekai replay 976c5a32 --model gpt-4o
    peekai replay 976c5a32 --model claude-3-5-sonnet-20241022
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.table import Table

from peekai.cli.console import console, get_storage
from peekai.core.models import SpanKind, SpanStatus
from peekai.replay.engine import ReplayEngine

_STATUS_STYLE = {
    SpanStatus.OK: ("ok", "✓"),
    SpanStatus.ERROR: ("error", "✗"),
    SpanStatus.PENDING: ("pending", "⏳"),
}


def replay(
    trace_id: str = typer.Argument(..., help="Trace ID to replay (full or first 8 chars)"),
    model: Annotated[
        str | None,
        typer.Option("--model", "-m", help="Override model for all LLM spans"),
    ] = None,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="API key (overrides OPENAI_API_KEY env var)"),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="Custom base URL for OpenAI-compatible endpoints"),
    ] = None,
    tool_override: Annotated[
        list[str] | None,
        typer.Option(
            "--tool", "-t",
            help="Override a tool response: 'tool_name=response'. Repeatable.",
        ),
    ] = None,
) -> None:
    """Re-run a past trace. Optionally swap the model or inject tool responses."""

    # Parse tool overrides: ["search=hello world", "calc=42"] → {"search": "hello world"}
    tool_overrides: dict[str, str] = {}
    for item in tool_override or []:
        if "=" not in item:
            console.print(f"[error]Invalid --tool format '{item}'. Use: tool_name=response[/error]")
            raise typer.Exit(1)
        k, v = item.split("=", 1)
        tool_overrides[k.strip()] = v.strip()

    storage = get_storage()
    engine = ReplayEngine(
        storage=storage,
        model_override=model,
        tool_overrides=tool_overrides,
        api_key=api_key,
        base_url=base_url,
    )

    console.print()
    console.print(f"[label]Replaying trace[/label] [dim]{trace_id}[/dim]", end="")
    if model:
        console.print(f"  [model]→ {model}[/model]", end="")
    if tool_overrides:
        console.print(f"  [dim]tool overrides: {list(tool_overrides.keys())}[/dim]", end="")
    console.print()
    console.print()

    try:
        result = engine.replay(trace_id)
    except ValueError as e:
        console.print(f"[error]{e}[/error]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[error]Replay failed: {e}[/error]")
        raise typer.Exit(1)

    orig = result.original
    rep = result.replayed

    # ── Summary table ─────────────────────────────────────────────
    table = Table(
        show_header=True,
        header_style="bold",
        border_style="dim",
        title="Replay comparison",
    )
    table.add_column("", style="label", width=14)
    table.add_column("Original", justify="right")
    table.add_column("Replayed", justify="right")
    table.add_column("Δ", justify="right")

    def delta(a: float, b: float, fmt: str = ".0f") -> str:
        d = b - a
        sign = "+" if d > 0 else ""
        return f"[ok]{sign}{d:{fmt}}[/ok]" if d <= 0 else f"[error]{sign}{d:{fmt}}[/error]"

    table.add_row(
        "Tokens",
        str(orig.total_tokens),
        str(rep.total_tokens),
        delta(orig.total_tokens, rep.total_tokens),
    )
    table.add_row(
        "Cost (USD)",
        f"${orig.total_cost_usd:.6f}",
        f"${rep.total_cost_usd:.6f}",
        delta(orig.total_cost_usd, rep.total_cost_usd, ".6f"),
    )
    dur_orig = orig.duration_ms or 0
    dur_rep = rep.duration_ms or 0
    table.add_row(
        "Duration",
        f"{dur_orig:.0f}ms",
        f"{dur_rep:.0f}ms",
        delta(dur_orig, dur_rep),
    )

    console.print(table)
    console.print()

    # ── Span-by-span diff ─────────────────────────────────────────
    console.print("[bold]Span comparison[/bold]\n")

    for orig_span, rep_span in result.span_pairs:
        if orig_span.kind != SpanKind.LLM:
            console.print(f"  [dim]⊘ {orig_span.name} (skipped — not an LLM span)[/dim]")
            continue

        o_style, o_icon = _STATUS_STYLE.get(orig_span.status, ("dim", "?"))
        r_style, r_icon = _STATUS_STYLE.get(
            rep_span.status if rep_span else SpanStatus.ERROR, ("dim", "?")
        )

        console.print(
            f"  [bold]{orig_span.name}[/bold]  "
            f"[{o_style}]{o_icon} orig[/{o_style}]  →  "
            f"[{r_style}]{r_icon} replay[/{r_style}]"
        )

        if rep_span:
            # Show output diff
            if orig_span.output != rep_span.output:
                console.print("    [dim]── original output ──[/dim]")
                console.print(f"    {orig_span.output[:200]}{'…' if len(orig_span.output) > 200 else ''}")
                console.print("    [dim]── replayed output ──[/dim]")
                console.print(f"    {rep_span.output[:200]}{'…' if len(rep_span.output) > 200 else ''}")
            else:
                console.print("    [dim]Output unchanged.[/dim]")

            tok_diff = rep_span.total_tokens - orig_span.total_tokens
            cost_diff = rep_span.cost_usd - orig_span.cost_usd
            sign_t = "+" if tok_diff > 0 else ""
            sign_c = "+" if cost_diff > 0 else ""
            console.print(
                f"    [dim]tokens: {orig_span.total_tokens} → {rep_span.total_tokens} "
                f"({sign_t}{tok_diff})  "
                f"cost: ${orig_span.cost_usd:.6f} → ${rep_span.cost_usd:.6f} "
                f"({sign_c}{cost_diff:.6f})[/dim]"
            )

            if rep_span.error:
                console.print(f"    [error]{rep_span.error_type}: {rep_span.error}[/error]")

        console.print()

    console.print(f"[dim]Replayed trace saved as:[/dim] [label]{rep.trace_id[:8]}[/label]")
    console.print(f"[dim]Run[/dim] [label]peekai view {rep.trace_id[:8]}[/label] [dim]to inspect it.[/dim]\n")
