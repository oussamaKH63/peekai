"""
Tests for the redaction pipeline.

Covers:
- Default token patterns (OpenAI/Anthropic/AWS/Bearer/PEM)
- Key-aware dict redaction (the main gap — dict form secrets)
- Recursive scrubbing through nested dicts and lists
- metadata redacted in both span and trace
- Custom callable and custom pattern list
- redact=False disables scrubbing
- Raw DB bytes never contain a planted secret
- capture_content=False short-circuits before redaction (efficiency)
- Metrics always intact after redaction
- Known limitations documented (AWS secret key not caught)
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from peekai.core.models import SpanKind, SpanStatus
from peekai.core.redaction import _SENSITIVE_KEYS, build_redactor
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer


# ---------------------------------------------------------------------------
# build_redactor unit tests — token patterns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secret,description", [
    ("sk-abc123ABCDEFGHIJKLMNOP",                    "OpenAI key (short)"),
    ("sk-proj-abcdefghijklmnopqrstuvwxyz",            "OpenAI project key"),
    ("sk-ant-api03-abcdefghijklmnopqrstu",            "Anthropic key"),
    ("AKIAIOSFODNN7EXAMPLE",                          "AWS access key ID"),
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x", "Bearer token"),
    ("-----BEGIN PRIVATE KEY-----\nABCD\n-----END PRIVATE KEY-----", "PEM private key block"),
    ("-----BEGIN RSA PRIVATE KEY-----\nDATA\n-----END RSA PRIVATE KEY-----", "PEM RSA key"),
    ('{"api_key": "super-secret-value-here"}',        "JSON blob api_key field"),
    ('{"password": "hunter2hunter2hunter2"}',          "JSON blob password field"),
])
def test_default_token_patterns_catch_known_secrets(secret, description):
    redact = build_redactor(True)
    assert redact is not None
    result = redact(secret)
    assert "REDACTED" in str(result), f"Secret not redacted: {description}"
    assert secret not in str(result), f"Original secret still present: {description}"


def test_normal_text_is_not_modified():
    redact = build_redactor(True)
    assert redact is not None
    text = "The weather today is sunny and 22 degrees."
    assert redact(text) == text


# ---------------------------------------------------------------------------
# Key-aware dict redaction — THE main gap from the review
# ---------------------------------------------------------------------------

def test_dict_form_api_key_is_redacted():
    """{'api_key': 'hunter2'} must be redacted even though 'hunter2' matches no token pattern."""
    redact = build_redactor(True)
    assert redact is not None
    data = {"api_key": "hunter2hunter2"}
    result = redact(data)
    assert result["api_key"] == "[REDACTED]"


def test_dict_form_password_is_redacted():
    redact = build_redactor(True)
    assert redact is not None
    result = redact({"password": "p@ssw0rd-not-token-shaped"})
    assert result["password"] == "[REDACTED]"


def test_dict_form_token_is_redacted():
    redact = build_redactor(True)
    assert redact is not None
    result = redact({"token": "my-custom-format-token-xyz"})
    assert result["token"] == "[REDACTED]"


def test_dict_form_authorization_is_redacted():
    redact = build_redactor(True)
    assert redact is not None
    result = redact({"authorization": "Basic dXNlcjpwYXNz"})
    assert result["authorization"] == "[REDACTED]"


def test_non_sensitive_dict_key_is_preserved():
    redact = build_redactor(True)
    assert redact is not None
    result = redact({"model": "gpt-4o", "temperature": 0.7})
    assert result["model"] == "gpt-4o"
    assert result["temperature"] == 0.7


def test_nested_dict_sensitive_key_is_redacted():
    """Secret nested inside a list of message dicts must still be caught."""
    redact = build_redactor(True)
    assert redact is not None
    data = [
        {"role": "user", "content": "hello"},
        {"role": "system", "api_key": "should-be-gone"},
    ]
    result = redact(data)
    assert result[1]["api_key"] == "[REDACTED]"
    assert result[0]["content"] == "hello"  # non-secret preserved


def test_all_sensitive_key_names_are_covered():
    """Spot-check the sensitive key set contains expected names."""
    for key in ("api_key", "password", "token", "secret", "authorization",
                "private_key", "access_token", "client_secret"):
        assert key in _SENSITIVE_KEYS, f"Missing sensitive key: {key}"


# ---------------------------------------------------------------------------
# Known limitation — AWS secret key NOT caught (document, not a bug)
# ---------------------------------------------------------------------------

def test_aws_secret_key_not_caught_by_default():
    """AWS 40-char secret keys have no prefix and cannot be caught without
    false positives.  This test documents the known limitation."""
    redact = build_redactor(True)
    assert redact is not None
    aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    result = redact(aws_secret)
    # We document that this is NOT redacted — test asserts the known behaviour
    assert aws_secret in result  # known gap, documented in module docstring


# ---------------------------------------------------------------------------
# Custom modes
# ---------------------------------------------------------------------------

def test_redact_false_returns_none():
    assert build_redactor(False) is None


def test_custom_callable_is_used():
    fn = lambda s: s.replace("hunter2", "[GONE]")
    redact = build_redactor(fn)
    assert redact is not None
    assert redact("password is hunter2") == "password is [GONE]"


def test_custom_callable_still_applies_key_aware_redaction():
    """Key-aware dict redaction applies even with a custom callable."""
    fn = lambda s: s  # no-op string scrubber
    redact = build_redactor(fn)
    assert redact is not None
    result = redact({"api_key": "my-custom-secret"})
    assert result["api_key"] == "[REDACTED]"


def test_custom_pattern_list_is_used():
    pattern = re.compile(r"TOKEN-[A-Z0-9]+")
    redact = build_redactor([pattern])
    assert redact is not None
    result = redact("auth=TOKEN-ABC123XYZ")
    assert "TOKEN-ABC123XYZ" not in result
    assert "REDACTED" in result


# ---------------------------------------------------------------------------
# Storage integration — secrets never reach the DB
# ---------------------------------------------------------------------------

def _make_span_with_secret(tracer: Tracer, secret: str) -> object:
    tracer.start_trace("redaction_test")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": f"My key is {secret}"}]
    span.output = f"Your key {secret} is noted."
    span.tool_calls = [{"function": "lookup", "arguments": {"token": secret}}]
    span.error = f"Failed with key {secret}"
    span.metadata = {"api_key": secret, "run": "test"}
    span.input_tokens = 10
    span.output_tokens = 5
    span.total_tokens = 15
    tracer.finish_span(span, SpanStatus.ERROR)
    return span


def test_secret_never_written_to_db_bytes(tmp_path):
    """Raw SQLite file bytes must not contain the planted token-shaped secret."""
    secret = "sk-proj-TestSecretKey1234567890AB"
    db_file = tmp_path / "redact_test.db"
    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    _make_span_with_secret(tracer, secret)
    storage.close()
    assert secret.encode() not in db_file.read_bytes()


def test_dict_form_secret_never_written_to_db_bytes(tmp_path):
    """Dict-form secret (non-token-shaped) under a sensitive key must not reach disk."""
    secret = "hunter2-not-token-shaped"
    db_file = tmp_path / "dict_secret.db"
    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    tracer.start_trace("t")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": "hello"}]
    span.metadata = {"api_key": secret}
    tracer.finish_span(span, SpanStatus.OK)
    storage.close()
    assert secret.encode() not in db_file.read_bytes()


def test_span_metadata_is_redacted(tmp_path):
    """span.metadata sensitive keys must be redacted before persistence."""
    secret = "sk-proj-MetaTest1234567890ABCDEFG"
    db_file = tmp_path / "meta_span.db"
    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    tracer.start_trace("t")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.metadata = {"api_key": secret, "run_id": "abc"}
    tracer.finish_span(span, SpanStatus.OK)
    saved = storage.get_spans(span.trace_id)[0]
    assert secret not in str(saved.metadata)
    assert saved.metadata.get("run_id") == "abc"  # non-secret preserved
    storage.close()


def test_trace_metadata_is_redacted(tmp_path):
    """trace.metadata sensitive keys must be redacted before persistence."""
    secret = "sk-proj-TraceMetaTest1234567890AB"
    db_file = tmp_path / "meta_trace.db"
    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    trace = tracer.start_trace("t", metadata={"api_key": secret, "env": "test"})
    tracer.finish_trace(trace)
    saved = storage.get_trace(trace.trace_id)
    assert saved is not None
    assert secret not in str(saved.metadata)
    assert saved.metadata.get("env") == "test"
    storage.close()


def test_metrics_intact_after_redaction(tmp_path):
    secret = "sk-proj-MetricsTest12345678901234"
    db_file = tmp_path / "metrics.db"
    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    span = _make_span_with_secret(tracer, secret)
    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert saved.input_tokens == 10
    assert saved.output_tokens == 5
    assert saved.total_tokens == 15
    assert saved.model == "gpt-4o"
    storage.close()


def test_redact_false_preserves_secret(tmp_path):
    secret = "sk-proj-NoRedactTest1234567890ABCD"
    db_file = tmp_path / "no_redact.db"
    storage = Storage(db_file, redact=False)
    tracer = Tracer(storage=storage)
    span = _make_span_with_secret(tracer, secret)
    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert secret in str(saved.input)
    storage.close()


def test_capture_content_false_skips_redaction_entirely(tmp_path):
    """capture_content=False blanks everything — redactor must not be called
    (efficiency: no wasted CPU on data that will be discarded)."""
    calls: list[str] = []

    def counting_redactor(s: str) -> str:
        calls.append(s)
        return s

    db_file = tmp_path / "skip_redact.db"
    storage = Storage(db_file, capture_content=False, redact=counting_redactor)
    tracer = Tracer(storage=storage)
    tracer.start_trace("t")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": "hello"}]
    span.output = "world"
    tracer.finish_span(span, SpanStatus.OK)

    assert calls == [], "Redactor must not be called when capture_content=False"
    storage.close()
