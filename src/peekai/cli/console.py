"""Shared Rich console and storage accessor for CLI commands."""

from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

from peekai.core.storage import Storage

_theme = Theme(
    {
        "ok":          "bold green",
        "error":       "bold red",
        "pending":     "bold yellow",
        "dim":         "dim white",
        "label":       "bold cyan",
        "cost":        "bold magenta",
        "model":       "bold blue",
        # banner / welcome screen
        "brand":       "bold white",
        "brand_dim":   "dim white",
        "accent":      "cyan",
        "muted":       "bright_black",
        "cmd":         "bold cyan",
        "cmd_desc":    "white",
        "version_tag": "dim cyan",
    }
)

console = Console(theme=_theme)


def get_storage() -> Storage:
    """Return the default Storage instance (reads from ~/.peekai/peekai.db)."""
    return Storage()
