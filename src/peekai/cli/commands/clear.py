"""peekai clear — wipe all local trace data."""

from __future__ import annotations

import typer

from peekai.cli.console import console, get_storage


def clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Wipe all traces and spans from local storage."""
    if not yes:
        confirmed = typer.confirm(
            "This will permanently delete all local traces. Continue?",
            default=False,
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit()

    storage = get_storage()
    storage.delete_all()
    storage.close()
    console.print("[ok]✓ All traces cleared.[/ok]")
