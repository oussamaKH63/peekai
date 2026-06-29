"""
Tests for the redaction pipeline.

Key assertions:
- Default patterns catch planted secrets in every span field.
- The raw DB bytes never contain the secret (not just the returned object).
- User callable and user pattern list are respected.
- redact=False disables scrubbing entirely.
- Redaction runs before capture_content blanking (order check).
- Non-secret content is preserved unchanged.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from peekai.core.models import SpanKind, SpanStatus
from peekai.core.redaction import build_redactor
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer


# ---------------------------------------------------------------------------
# build_redactor unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secret,description", [
    ("sk-abc123ABCDEFGHIJKLMNOP",         "OpenAI key (short)"),
    ("sk-proj-abcdefghijklmnopqrstuvwxyz", "OpenAI project key"),
    ("sk-ant-api03-abcdefghijklmnopqrstu", "Anthropic key"),
    ("AKIAIOSFODNN7EXAMPLE",               "AWS access key ID"),
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig", "Bearer token"),
    ('{"api_key": "super-secret-value"}',  "JSON api_key field"),
    ('{"password": "hunter2hunter2"}',     "JSON password field"),
])
def test_default_patterns_catch_known_secrets(secret, description):
    redact = build_redactor(True)
    assert redact is not None
    result = redact(secret)
    assert "REDACTED" in result, f"Secret not redacted: {description}"
    assert secret not in result, f"Original secret still present: {description}"


def test_normal_text_is_not_modified():
    redact = build_redactor(True)
    assert redact is not None
    text = "The weather today is sunny and 22 degrees."
    assert redact(text) == text


def test_redact_false_returns_none():
    assert build_redactor(False) is None


def test_custom_callable_is_used():
    fn = lambda s: s.replace("hunter2", "[GONE]")
    redact = build_redactor(fn)
    assert redact is not None
    assert redact("password is hunter2") == "password is [GONE]"


def test_custom_pattern_list_is_used():
    pattern = re.compile(r"TOKEN-[A-Z0-9]+")
    redact = build_redactor([pattern])
    assert redact is not None
    result = redact("auth=TOKEN-ABC123XYZ")
    assert "TOKEN-ABC123XYZ" not in result
    assert "REDACTED" in result


def test_redaction_recurses_into_dicts_and_lists():
    redact = build_redactor(True)
    assert redact is not None
    data = [
        {"role": "user", "content": "my key is sk-abc123ABCDEFGHIJKLMNOP"},
        {"role": "assistant", "content": "noted"},
    ]
    result = redact(data)
    assert isinstance(result, list)
    assert "sk-abc123ABCDEFGHIJKLMNOP" not in str(result)
    assert "noted" in str(result)  # non-secret preserved


# ---------------------------------------------------------------------------
# Storage integration — secret never reaches the DB
# ---------------------------------------------------------------------------

def _make_span_with_secret(tracer: Tracer, secret: str) -> object:
    tracer.start_trace("redaction_test")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": f"My key is {secret}, help me."}]
    span.output = f"Sure, your key {secret} is noted."
    span.tool_calls = [{"function": "lookup", "arguments": {"token": secret}}]
    span.error = f"Failed with key {secret}"
    span.input_tokens = 10
    span.output_tokens = 5
    span.total_tokens = 15
    tracer.finish_span(span, SpanStatus.ERROR)
    return span


def test_secret_never_written_to_db_bytes(tmp_path):
    """Assert the raw SQLite file bytes never contain the planted secret."""
    secret = "sk-proj-TestSecretKey1234567890AB"
    db_file = tmp_path / "redact_test.db"

    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    _make_span_with_secret(tracer, secret)
    storage.close()

    raw_bytes = db_file.read_bytes()
    assert secret.encode() not in raw_bytes, "Secret found in raw DB bytes!"


def test_redacted_span_fields_in_retrieved_object(tmp_path):
    """Loaded span object must not contain the original secret."""
    secret = "sk-ant-api03-RedactionTest1234567890"
    db_file = tmp_path / "redact_obj.db"

    storage = Storage(db_file, redact=True)
    tracer = Tracer(storage=storage)
    span = _make_span_with_secret(tracer, secret)

    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert secret not in str(saved.input)
    assert secret not in saved.output
    assert secret not in str(saved.tool_calls)
    assert secret not in (saved.error or "")
    storage.close()


def test_metrics_intact_after_redaction(tmp_path):
    """Token counts and cost must survive redaction unchanged."""
    secret = "sk-proj-MetricsTest1234567890ABCDE"
    db_file = tmp_path / "redact_metrics.db"

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
    """When redact=False the secret must be stored as-is."""
    secret = "sk-proj-NoRedactTest1234567890ABCD"
    db_file = tmp_path / "no_redact.db"

    storage = Storage(db_file, redact=False)
    tracer = Tracer(storage=storage)
    span = _make_span_with_secret(tracer, secret)

    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert secret in str(saved.input), "Secret should be present when redact=False"
    storage.close()


def test_custom_callable_redactor_in_storage(tmp_path):
    """A user-supplied callable must be applied to span content."""
    my_secret = "MYSECRET-TOKEN-XYZ"
    db_file = tmp_path / "custom_redact.db"

    storage = Storage(db_file, redact=lambda s: s.replace(my_secret, "[GONE]"))
    tracer = Tracer(storage=storage)
    tracer.start_trace("t")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": f"token={my_secret}"}]
    span.output = f"got {my_secret}"
    tracer.finish_span(span, SpanStatus.OK)

    saved = storage.get_spans(span.trace_id)[0]
    assert my_secret not in str(saved.input)
    assert my_secret not in saved.output
    assert "[GONE]" in str(saved.input)
    storage.close()


def test_redaction_runs_before_capture_content_gate(tmp_path):
    """Even with capture_content=True, redaction must fire — no secret in DB."""
    secret = "sk-proj-OrderTest12345678901234567"
    db_file = tmp_path / "order_test.db"

    # capture_content=True AND redact=True — content stored but scrubbed
    storage = Storage(db_file, capture_content=True, redact=True)
    tracer = Tracer(storage=storage)
    span = _make_span_with_secret(tracer, secret)

    raw_bytes = db_file.read_bytes()
    assert secret.encode() not in raw_bytes
    storage.close()
