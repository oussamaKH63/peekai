"""
PeekAI CLI welcome banner.

Shown when `peekai` is invoked with no arguments. Styled after modern CLI
tools (Claude Code, gh, etc.) — brand colors from peekai-icon.svg,
Braille logo art + block wordmark + command overview.

Brand colors (from peekai-icon.svg):
  Primary  #ff6600  — orange
  Navy     #001f5b  — dark body
"""

from __future__ import annotations

from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from peekai.cli.console import console
from peekai.core.storage import _DEFAULT_DB_PATH

# ---------------------------------------------------------------------------
# Brand colors
# ---------------------------------------------------------------------------
ORANGE = "#ff6600"
DIM_FG = "#666666"
WHITE  = "#e8e8e8"

# ---------------------------------------------------------------------------
# Block wordmark
# ---------------------------------------------------------------------------
_WORDMARK_LINES = [
    " ██████╗ ███████╗███████╗██╗  ██╗ █████╗ ██╗",
    " ██╔══██╗██╔════╝██╔════╝██║ ██╔╝██╔══██╗██║",
    " ██████╔╝█████╗  █████╗  █████╔╝ ███████║██║",
    " ██╔═══╝ ██╔══╝  ██╔══╝  ██╔═██╗ ██╔══██║██║",
    " ██║     ███████╗███████╗██║  ██╗██║  ██║██║",
    " ╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝",
]

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
_COMMANDS = [
    ("list",         "Show recent traces"),
    ("view <id>",    "Full span waterfall with I/O"),
    ("map  <id>",    "ASCII agent flow tree"),
    ("stats",        "Token & cost totals by model"),
    ("replay <id>",  "Re-run a trace (supports --model, --tool)"),
    ("ui",           "Launch the web dashboard"),
    ("clear",        "Wipe local storage"),
]


def _make_commands_table() -> Table:
    tbl = Table(
        show_header=False,
        box=None,
        padding=(0, 2, 0, 0),
        expand=False,
    )
    tbl.add_column("cmd",  no_wrap=True, min_width=22)
    tbl.add_column("desc", no_wrap=False)
    for cmd, desc in _COMMANDS:
        tbl.add_row(
            Text(cmd,  style=f"bold {ORANGE}"),
            Text(desc, style=WHITE),
        )
    return tbl


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def print_banner() -> None:
    """Render the full welcome screen to the console."""
    from peekai import __version__

    console.print()

    # ── Block wordmark with vertical fade ────────────────────────
    # Linear interpolation: #ff6600 (orange) → #646464 (grey)
    _GRADIENT = [
        "#ff6600",  # row 0
        "#e06514",  # row 1
        "#c16528",  # row 2
        "#a2643c",  # row 3
        "#836450",  # row 4
        "#646464",  # row 5 — grey
    ]
    for line, color in zip(_WORDMARK_LINES, _GRADIENT):
        console.print(Text(f"  {line}", style=f"bold {color}"))

    console.print()

    # ── Tagline + version ─────────────────────────────────────────
    console.print(Text.assemble(
        ("  Lightweight, local-first observability for Python AI agents.", WHITE),
    ))
    console.print(Text.assemble(
        ("  version ", DIM_FG),
        (f"v{__version__}", ORANGE),
        ("  ·  ", DIM_FG),
        ("db ", DIM_FG),
        (str(_DEFAULT_DB_PATH), DIM_FG),
    ))
    console.print()

    # ── Commands panel ────────────────────────────────────────────
    console.print(Padding(
        Panel(
            _make_commands_table(),
            title=Text("Commands", style=f"bold {WHITE}"),
            title_align="left",
            border_style=DIM_FG,
            padding=(0, 1),
        ),
        (0, 0, 0, 2),
    ))

    # ── Footer ────────────────────────────────────────────────────
    console.print()
    console.print(Text.assemble(
        ("  peekai ", DIM_FG),
        ("<command> --help", ORANGE),
        ("  for detailed usage of any command.", DIM_FG),
    ))
    console.print()
