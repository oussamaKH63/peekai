"""
PeekAI CLI — inspect traces without leaving your terminal.

Commands:
    peekai list              — show last 10 traces
    peekai view <trace-id>   — pretty-print a trace
    peekai stats             — total cost, tokens, runs
    peekai clear             — wipe local storage
    peekai ui                — launch Streamlit UI
    peekai replay <trace-id> — re-run a past trace
    peekai map <trace-id>    — ASCII agent flow tree
"""

from __future__ import annotations

from typing import Annotated

import typer

from peekai.cli.commands.clear import clear
from peekai.cli.commands.list_traces import list_traces
from peekai.cli.commands.map_trace import map_trace
from peekai.cli.commands.replay import replay
from peekai.cli.commands.stats import stats
from peekai.cli.commands.ui import ui
from peekai.cli.commands.view import view


def _version_callback(value: bool) -> None:
    if value:
        from peekai import __version__
        typer.echo(f"peekai {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="peekai",
    help="👀 Lightweight, local-first observability for Python AI agents.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    pass


app.command("list")(list_traces)
app.command("view")(view)
app.command("stats")(stats)
app.command("clear")(clear)
app.command("ui")(ui)
app.command("replay")(replay)
app.command("map")(map_trace)


if __name__ == "__main__":
    app()
