"""
Redaction pipeline for PeekAI trace data.

Scrubs well-known secret patterns from span fields before they are persisted
to SQLite.  The redactor runs as a single chokepoint in ``Storage.save_span``
and ``Storage.save_trace`` so no secret can reach the database regardless of
which SDK patch produced it.

Design
------
Two complementary strategies are applied on every value:

1. **Key-aware dict redaction** — when recursing a dict, if the *key* matches
   a sensitive name (``api_key``, ``password``, ``token``, etc.) the *entire
   value* is replaced with ``[REDACTED]`` regardless of its content or shape.
   This catches plain-dict secrets like ``{'api_key': 'hunter2'}`` that are
   invisible to token-pattern matching.

2. **Token-pattern string scrubbing** — regex patterns applied to every string
   value catch token-shaped secrets (OpenAI/Anthropic keys, AWS access key IDs,
   Bearer tokens, PEM blocks) that appear anywhere in string content, including
   inside serialised JSON blobs.

Default patterns
----------------
- OpenAI API keys          ``sk-...`` / ``sk-proj-...`` / ``sk-o1-...``
- Anthropic API keys       ``sk-ant-...``  (also caught by the sk- pattern above)
- AWS access key IDs       ``AKIA[A-Z0-9]{16}``
- Bearer / token headers   ``Authorization: Bearer <token>``
- PEM private-key blocks   ``-----BEGIN ... KEY-----``
- JSON-blob secret fields  ``"api_key": "..."`` etc. in serialised strings

Known limitations
-----------------
- AWS *secret* access keys (40-char, no prefix) cannot be caught without
  unacceptable false-positive rates.  The real boundary is ``0600`` file
  permissions + ``capture_content=False``.  Redaction is defense-in-depth,
  not a guarantee.
- GCP service-account JSON, raw JWTs without a Bearer prefix, and other
  vendor-specific formats are not matched by default.  Use a custom callable
  or pattern list for those.

Usage
-----
    peekai.init()                          # True  — default patterns
    peekai.init(redact=False)              # False — disable entirely
    peekai.init(redact=my_fn)             # callable(str) -> str
    peekai.init(redact=[re.compile(...)]) # list of compiled patterns
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Replacement sentinel
# ---------------------------------------------------------------------------

_REPLACEMENT = "[REDACTED]"

# ---------------------------------------------------------------------------
# Sensitive key names — dict values under these keys are fully redacted
# regardless of content.
# ---------------------------------------------------------------------------

_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "api_key", "apikey", "api-key",
    "secret", "secret_key", "secretkey", "secret-key",
    "access_token", "accesstoken", "access-token",
    "auth_token", "authtoken", "auth-token",
    "password", "passwd", "pass",
    "token",
    "private_key", "privatekey", "private-key",
    "authorization",
    "x-api-key",
    "client_secret", "clientsecret",
})


def _is_sensitive_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return key.lower().replace(" ", "_") in _SENSITIVE_KEYS


# ---------------------------------------------------------------------------
# Token-pattern string scrubbing
# ---------------------------------------------------------------------------

_DEFAULT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # OpenAI keys: sk-  sk-proj-  sk-o1-  followed by alphanumeric/dash chars
    # (also catches sk-ant- so a separate Anthropic pattern is unnecessary)
    (re.compile(r"sk-(?:proj-|o1-|ant-[a-z0-9]+-)?[A-Za-z0-9_\-]{20,}"), _REPLACEMENT),
    # AWS access key IDs: AKIA + 16 uppercase alphanumerics
    (re.compile(r"AKIA[A-Z0-9]{16}"), _REPLACEMENT),
    # Bearer tokens in Authorization headers
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]{8,}"), r"\1" + _REPLACEMENT),
    # PEM private/public key blocks
    (re.compile(r"-----BEGIN [A-Z ]*(?:PRIVATE|PUBLIC) KEY-----.*?-----END [A-Z ]*(?:PRIVATE|PUBLIC) KEY-----", re.DOTALL), _REPLACEMENT),
    # Generic secret fields in serialised JSON blobs (string form only —
    # dict form is handled key-aware in _scrub_value below)
    (
        re.compile(
            r'("(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|password|passwd|auth[_\-]?token|private[_\-]?key)"\s*:\s*")[^"]{4,}(")',
        ),
        r"\1" + _REPLACEMENT + r"\2",
    ),
]


def _scrub_string(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> str:
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Recursive scrubber — key-aware for dicts
# ---------------------------------------------------------------------------

def _scrub_value(
    value: Any,
    scrub_str: Callable[[str], str],
) -> Any:
    """Recursively scrub a value.

    - dict: if the key is sensitive, replace the *entire* value with
      ``[REDACTED]``; otherwise recurse into the value.
    - list: recurse into each element.
    - str: apply token-pattern scrubbing.
    - anything else: return unchanged.
    """
    if isinstance(value, str):
        return scrub_str(value)
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                # Redact the whole value — don't inspect content
                result[k] = _REPLACEMENT if v else v
            else:
                result[k] = _scrub_value(v, scrub_str)
        return result
    if isinstance(value, list):
        return [_scrub_value(item, scrub_str) for item in value]
    return value


# ---------------------------------------------------------------------------
# Public type alias + factory
# ---------------------------------------------------------------------------

RedactOption = bool | Callable[[str], str] | list[re.Pattern[str]]


def build_redactor(redact: RedactOption) -> Callable[[Any], Any] | None:
    """Return a redactor function, or None if redaction is disabled.

    Args:
        redact: ``True``  — use built-in default patterns + key-aware scrubbing.
                ``False`` — disable redaction entirely (returns None).
                callable  — use as a string scrubber; key-aware dict logic
                            still applies on top.
                list      — treat as compiled ``re.Pattern`` objects substituted
                            with ``[REDACTED]``; key-aware dict logic still applies.

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
        user_fn: Callable[[str], str] = redact  # type: ignore[assignment]
        return lambda value: _scrub_value(value, user_fn)

    if isinstance(redact, list):
        user_patterns = [(p, _REPLACEMENT) for p in redact]

        def _pattern_scrub(text: str) -> str:
            return _scrub_string(text, user_patterns)

        return lambda value: _scrub_value(value, _pattern_scrub)

    raise TypeError(
        f"redact must be bool, callable, or list[re.Pattern]; got {type(redact)}"
    )
