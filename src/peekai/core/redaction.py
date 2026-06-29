"""
Redaction pipeline for PeekAI trace data.

Scrubs well-known secret patterns from span fields before they are persisted
to SQLite.  The redactor runs as a single chokepoint in ``Storage.save_span``
so no secret can reach the database regardless of which SDK patch produced it.

Default patterns
----------------
- OpenAI API keys          sk-...  /  sk-proj-...  /  sk-o1-...
- Anthropic API keys       sk-ant-...
- AWS access key IDs       AKIA[A-Z0-9]{16}
- Bearer / token headers   Authorization: Bearer <token>
- Generic secret fields    "api_key": "...", "password": "...", etc.

Usage
-----
Three modes, controlled by the ``redact`` argument to ``peekai.init()``:

    peekai.init()                    # True  — apply default patterns
    peekai.init(redact=False)        # False — disable redaction entirely
    peekai.init(redact=my_fn)        # callable(str) -> str — custom scrubber
    peekai.init(redact=[re.compile(...)])  # list of compiled patterns
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Default secret patterns
# ---------------------------------------------------------------------------

_REPLACEMENT = "[REDACTED]"

# Each tuple is (compiled pattern, replacement string).
_DEFAULT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # OpenAI keys: sk-  sk-proj-  sk-o1-  followed by alphanumeric/dash chars
    (re.compile(r"sk-(?:proj-|o1-)?[A-Za-z0-9_\-]{20,}"), _REPLACEMENT),
    # Anthropic keys: sk-ant- prefix
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), _REPLACEMENT),
    # AWS access key IDs: AKIA + 16 uppercase alphanumerics
    (re.compile(r"AKIA[A-Z0-9]{16}"), _REPLACEMENT),
    # Bearer tokens in Authorization headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]{8,}"), r"\1" + _REPLACEMENT),
    # Generic key/value patterns in JSON-like text: "api_key": "...", "password": "..."
    (
        re.compile(
            r'(?i)("(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|password|passwd|auth[_\-]?token|private[_\-]?key)"\s*:\s*")[^"]{4,}(")',
            re.DOTALL,
        ),
        r"\1" + _REPLACEMENT + r"\2",
    ),
]


# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

# redact param accepted by peekai.init() and Storage
RedactOption = bool | Callable[[str], str] | list[re.Pattern[str]]


# ---------------------------------------------------------------------------
# Core scrub helpers
# ---------------------------------------------------------------------------

def _scrub_string(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> str:
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


def _scrub_value(value: Any, scrub: Callable[[str], str]) -> Any:
    """Recursively scrub strings inside dicts, lists, and plain strings."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {k: _scrub_value(v, scrub) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_value(item, scrub) for item in value]
    return value


# ---------------------------------------------------------------------------
# Redactor factory
# ---------------------------------------------------------------------------

def build_redactor(redact: RedactOption) -> Callable[[Any], Any] | None:
    """Return a redactor function, or None if redaction is disabled.

    Args:
        redact: ``True``  — use built-in default patterns.
                ``False`` — disable redaction entirely (returns None).
                callable  — use as a string scrubber directly.
                list      — treat as a list of compiled ``re.Pattern`` objects,
                            each substituted with ``[REDACTED]``.

    Returns:
        A callable ``(value: Any) -> Any`` that recursively scrubs the value,
        or ``None`` if ``redact`` is ``False``.
    """
    if redact is False:
        return None

    if redact is True:
        patterns = _DEFAULT_PATTERNS

        def _default_scrub(text: str) -> str:
            return _scrub_string(text, patterns)

        return lambda value: _scrub_value(value, _default_scrub)

    if callable(redact):
        # User-supplied string → string function
        user_fn: Callable[[str], str] = redact  # type: ignore[assignment]
        return lambda value: _scrub_value(value, user_fn)

    if isinstance(redact, list):
        # List of compiled re.Pattern — substitute each with [REDACTED]
        user_patterns = [(p, _REPLACEMENT) for p in redact]

        def _pattern_scrub(text: str) -> str:
            return _scrub_string(text, user_patterns)

        return lambda value: _scrub_value(value, _pattern_scrub)

    raise TypeError(
        f"redact must be bool, callable, or list[re.Pattern]; got {type(redact)}"
    )
