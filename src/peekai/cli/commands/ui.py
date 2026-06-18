"""peekai ui — launch the Streamlit dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from peekai.cli.console import console


def ui(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run the UI on"),
) -> None:
    """Launch the PeekAI Streamlit dashboard."""
    app_path = Path(__file__).parent.parent.parent / "ui" / "app.py"

    if not app_path.exists():
        console.print("[error]UI app not found. This will be available in Phase 3.[/error]")
        raise typer.Exit(1)

    console.print(f"[ok]Launching PeekAI UI on http://localhost:{port}[/ok]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port)],
            check=True,
        )
    except KeyboardInterrupt:
        console.print("\n[dim]UI stopped.[/dim]")
    except FileNotFoundError:
        console.print('[error]streamlit not found. Install it with: pip install "peekai[ui]"[/error]')
        raise typer.Exit(1)
