"""
Active-tracer registry for the SDK patches.

The SDK monkey-patches are installed exactly once, but ``peekai.init()`` may be
called more than once (e.g. with a different ``db_path``). Routing every patched
call through this registry means the installed patches always use the most
recently initialised :class:`~peekai.core.tracer.Tracer`, instead of one captured
in a closure at patch time.

If no tracer is registered, patched calls run untraced.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from peekai.core.tracer import Tracer

_tracer: Tracer | None = None


def set_tracer(tracer: Tracer) -> None:
    """Register the tracer that patched SDK calls should use."""
    global _tracer
    _tracer = tracer


def get_tracer() -> Tracer | None:
    """Return the active tracer, or None if PeekAI has not been initialised."""
    return _tracer
