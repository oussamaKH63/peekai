"""
PeekAI — Lightweight, local-first observability and debugging for Python AI agents.
"""

from peekai.core.tracer import Tracer
from peekai.core.storage import Storage

__version__ = "0.1.0"
__all__ = ["Tracer", "Storage", "init", "trace"]


def init(**kwargs) -> None:  # type: ignore[no-untyped-def]
    """
    Initialize PeekAI and auto-patch all installed AI SDKs.

    Usage:
        import peekai
        peekai.init()
    """
    # Implemented in Phase 1
    raise NotImplementedError("peekai.init() will be implemented in Phase 1")


def trace(name: str | None = None):  # type: ignore[no-untyped-def]
    """
    Decorator to trace an agent run as a top-level trace.

    Usage:
        @peekai.trace()
        def run_agent():
            ...
    """
    # Implemented in Phase 1
    raise NotImplementedError("@peekai.trace() will be implemented in Phase 1")
