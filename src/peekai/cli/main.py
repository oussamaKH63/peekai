# CLI entry point — implemented in Phase 2
import typer

app = typer.Typer(
    name="peekai",
    help="👀 Lightweight, local-first observability for Python AI agents.",
    no_args_is_help=True,
)

if __name__ == "__main__":
    app()
