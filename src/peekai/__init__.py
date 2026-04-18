"""
PeekAI — Lightweight, local-first observability and debugging for Python AI agents.

Quickstart:
    import peekai
    peekai.init()

    # All OpenAI / Anthropic / LiteLLM calls are now traced automatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer

__version__ = "0.1.0"
__all__ = [
    "init",
    "trace",
    "tool",
    "agent",
    "Tracer",
    "Storage",
    "Trace",
    "Span",
    "SpanKind",
    "SpanStatus",
]

# Module-level default tracer — created on first call to init()
_tracer: Tracer | None = None


def init(
    db_path: str | Path | None = None,
    openai: bool = True,
    anthropic: bool = True,
    litellm: bool = True,
) -> Tracer:
    """
    Initialize PeekAI and auto-patch all installed AI SDKs.

    Args:
        db_path:   Custom path for the SQLite database.
                   Defaults to ~/.peekai/peekai.db
        openai:    Patch the OpenAI SDK (default True).
        anthropic: Patch the Anthropic SDK (default True).
        litellm:   Patch LiteLLM (default True).

    Returns:
        The global Tracer instance.

    Usage:
        import peekai
        peekai.init()
    """
    global _tracer

    storage = Storage(db_path)
    _tracer = Tracer(storage=storage)

    if openai:
        from peekai.patches.openai_patch import patch as openai_patch
        openai_patch(_tracer)

    if anthropic:
        from peekai.patches.anthropic_patch import patch as anthropic_patch
        anthropic_patch(_tracer)

    if litellm:
        from peekai.patches.litellm_patch import patch as litellm_patch
        litellm_patch(_tracer)

    return _tracer


def trace(name: str | None = None) -> Any:
    """
    Decorator that wraps a function in a top-level Trace.

    Requires peekai.init() to have been called first.

    Usage:
        @peekai.trace("my_agent")
        def run_agent():
            ...

        @peekai.trace()
        async def run_async():
            ...
    """
    _require_init()
    assert _tracer is not None
    return _tracer.trace(name)


def tool(name: str | None = None) -> Any:
    """
    Decorator that wraps a tool function in a TOOL span.

    Requires peekai.init() to have been called first.

    Usage:
        @peekai.tool("search_web")
        def search(query: str) -> str:
            ...
    """
    _require_init()
    assert _tracer is not None
    return _tracer.tool(name)


def agent(name: str | None = None) -> Any:
    """
    Decorator that wraps a sub-agent function in an AGENT span.

    All LLM/tool calls inside the decorated function become children
    of this agent span in the waterfall tree.

    Requires peekai.init() to have been called first.

    Usage:
        @peekai.agent("researcher")
        def researcher_agent(task: str) -> str:
            ...
    """
    _require_init()
    assert _tracer is not None
    return _tracer.agent(name)


def get_tracer() -> Tracer:
    """Return the global Tracer. Raises if init() has not been called."""
    _require_init()
    assert _tracer is not None
    return _tracer


def _require_init() -> None:
    if _tracer is None:
        raise RuntimeError(
            "PeekAI is not initialised. Call peekai.init() before using decorators."
        )
