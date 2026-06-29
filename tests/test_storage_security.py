"""
Security tests for Storage — file permissions and capture_content gating.

Permission tests are POSIX-only (Linux / macOS). They are skipped on Windows
because chmod is effectively a no-op on win32 and we document that limitation
rather than pretending it works.
"""

from __future__ import annotations

import os
import stat

import pytest

from peekai.core.models import SpanKind, SpanStatus
from peekai.core.storage import Storage
from peekai.core.tracer import Tracer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_span(tracer: Tracer) -> object:
    """Create a finished span with realistic sensitive content."""
    tracer.start_trace("security_test")
    span = tracer.start_span("openai/gpt-4o", kind=SpanKind.LLM, model="gpt-4o", provider="openai")
    span.input = [{"role": "user", "content": "My API key is sk-abc123, help me debug."}]
    span.output = "Sure, here is the answer."
    span.raw_response = {"id": "resp-1", "model": "gpt-4o", "stop_reason": "stop"}
    span.tool_calls = [{"function": "search", "arguments": {"query": "secret"}}]
    span.error = "Something went wrong with token sk-abc123"
    span.input_tokens = 20
    span.output_tokens = 10
    span.total_tokens = 30
    span.cost_usd = 0.0001
    tracer.finish_span(span, SpanStatus.OK)
    return span


# ---------------------------------------------------------------------------
# File permission tests (POSIX only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name != "posix", reason="chmod semantics only apply on POSIX")
def test_default_permissions_under_permissive_umask(tmp_path):
    """Directory must be 0o700 and database must be 0o600 under a 022 umask."""
    old_umask = os.umask(0o022)
    try:
        db_file = tmp_path / "perms_test" / "peekai.db"
        storage = Storage(db_file)
        storage.close()

        dir_mode = stat.S_IMODE(db_file.parent.stat().st_mode)
        db_mode = stat.S_IMODE(db_file.stat().st_mode)

        assert dir_mode == 0o700, f"Expected dir 0o700, got {oct(dir_mode)}"
        assert db_mode == 0o600, f"Expected db 0o600, got {oct(db_mode)}"
    finally:
        os.umask(old_umask)


@pytest.mark.skipif(os.name != "posix", reason="chmod semantics only apply on POSIX")
def test_wal_shm_sidecars_are_owner_only(tmp_path):
    """WAL and SHM sidecar files must also be 0o600 when they exist."""
    old_umask = os.umask(0o022)
    try:
        db_file = tmp_path / "wal_test" / "peekai.db"
        storage = Storage(db_file)

        # Force a write so WAL materialises, then re-harden.
        tracer = Tracer(storage=storage)
        _make_span(tracer)

        # Re-apply hardening (simulates what __init__ does after _migrate).
        from peekai.core.storage import _harden_permissions
        _harden_permissions(db_file)

        for suffix in ("-wal", "-shm"):
            sidecar = db_file.with_name(db_file.name + suffix)
            if sidecar.exists():
                mode = stat.S_IMODE(sidecar.stat().st_mode)
                assert mode == 0o600, f"{sidecar.name}: expected 0o600, got {oct(mode)}"

        storage.close()
    finally:
        os.umask(old_umask)


# ---------------------------------------------------------------------------
# capture_content tests
# ---------------------------------------------------------------------------

def test_capture_content_true_default_preserves_raw_fields(tmp_path):
    """Default (capture_content=True) must store prompts, outputs, and tool calls."""
    storage = Storage(tmp_path / "full.db", capture_content=True)
    tracer = Tracer(storage=storage)
    span = _make_span(tracer)

    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert saved.input != []
    assert saved.output == "Sure, here is the answer."
    assert saved.tool_calls != []
    assert saved.error is not None
    storage.close()


def test_capture_content_false_blanks_all_raw_fields(tmp_path):
    """capture_content=False must strip input, output, raw_response, tool_calls, error."""
    storage = Storage(tmp_path / "meta.db", capture_content=False)
    tracer = Tracer(storage=storage)
    span = _make_span(tracer)

    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert saved.input == []
    assert saved.output == ""
    assert saved.raw_response == {}
    assert saved.tool_calls == []
    assert saved.error is None
    storage.close()


def test_capture_content_false_preserves_metrics(tmp_path):
    """capture_content=False must keep token counts, cost, timings, model, and status."""
    storage = Storage(tmp_path / "meta2.db", capture_content=False)
    tracer = Tracer(storage=storage)
    span = _make_span(tracer)

    saved = storage.get_spans(span.trace_id)[0]  # type: ignore[attr-defined]
    assert saved.model == "gpt-4o"
    assert saved.provider == "openai"
    assert saved.input_tokens == 20
    assert saved.output_tokens == 10
    assert saved.total_tokens == 30
    assert saved.cost_usd == pytest.approx(0.0001)
    assert saved.status == SpanStatus.OK
    assert saved.error_type is None  # no error was set via finish_with_error
    assert saved.ended_at is not None
    storage.close()
