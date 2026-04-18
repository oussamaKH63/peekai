"""
PeekAI CLI — inspect traces without leaving your terminal.

Commands:
    peekai list              — show last 10 traces
    peekai view <trace-id>   — pretty-print a trace
    peekai stats             — total cost, tokens, runs
    peekai clear             — wipe local storage
    peekai ui                — launch Streamlit UI
"""

from __future__ import annotations

import typer

from peekai.cli.commands.clear import clear
from peekai.cli.commands.list_traces import list_traces
from peekai.cli.commands.stats import stats
from peekai.cli.commands.ui import ui
from peekai.cli.commands.view import view

app = typer.Typer(
    name="peekai",
    help="👀 Lightweight, local-first observability for Python AI agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.command("list")(list_traces)
app.command("view")(view)
app.command("stats")(stats)
app.command("clear")(clear)
app.command("ui")(ui)


if __name__ == "__main__":
    app()
