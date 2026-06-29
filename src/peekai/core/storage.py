"""
SQLite-backed local storage for traces and spans.

Schema
------
traces  — one row per Trace
spans   — one row per Span, foreign-keyed to traces

Security
--------
On POSIX systems the trace directory is created with 0o700 and the database
(plus WAL/SHM sidecar files) is set to 0o600 after the first write transaction
so that only the owning user can read trace data.  On Windows chmod is a no-op
and this hardening is skipped; document the limitation rather than fighting it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from peekai.core.models import Span, SpanKind, SpanStatus, Trace
from peekai.core.redaction import RedactOption, build_redactor

_DEFAULT_DB_PATH = Path.home() / ".peekai" / "peekai.db"


def _harden_permissions(db_path: Path) -> None:
    """Set owner-only permissions on the database and its WAL/SHM sidecars.

    Only runs on POSIX (Linux/macOS).  On Windows chmod is effectively a no-op
    so we skip it entirely rather than giving a false sense of security.
    WAL and SHM files are created lazily by SQLite on the first write, so we
    check for their existence before attempting chmod.
    """
    if os.name != "posix":
        return
    try:
        db_path.chmod(0o600)
        for suffix in ("-wal", "-shm"):
            sidecar = db_path.with_name(db_path.name + suffix)
            if sidecar.exists():
                sidecar.chmod(0o600)
    except OSError:
        pass  # best-effort — never crash user code over a permission tweak

_CREATE_TRACES = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id            TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    ended_at            TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    total_input_tokens  INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens        INTEGER NOT NULL DEFAULT 0,
    total_cost_usd      REAL NOT NULL DEFAULT 0.0,
    metadata            TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_SPANS = """
CREATE TABLE IF NOT EXISTS spans (
    span_id         TEXT PRIMARY KEY,
    trace_id        TEXT NOT NULL,
    parent_span_id  TEXT,
    name            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'llm',
    model           TEXT NOT NULL DEFAULT '',
    provider        TEXT NOT NULL DEFAULT '',
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    input           TEXT NOT NULL DEFAULT '[]',
    output          TEXT NOT NULL DEFAULT '',
    raw_response    TEXT NOT NULL DEFAULT '{}',
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0.0,
    tool_calls      TEXT NOT NULL DEFAULT '[]',
    error           TEXT,
    error_type      TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
)
"""


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class Storage:
    """
    Manages all read/write operations against the local SQLite database.

    Args:
        db_path:         Path to the SQLite database file.
                         Defaults to ``~/.peekai/peekai.db``.
        capture_content: When ``True`` (default) raw prompts, completions,
                         tool-call arguments, and error messages are stored.
                         Set to ``False`` to retain only timing, token counts,
                         costs, and status — useful in shared or regulated
                         environments where prompt content is sensitive.
        redact:          Controls secret scrubbing before persistence.
                         ``True`` (default) — apply built-in patterns for
                         OpenAI/Anthropic/AWS keys, bearer tokens, and common
                         secret fields.  ``False`` — disable entirely.
                         A callable ``str -> str`` or a list of compiled
                         ``re.Pattern`` objects can be passed for custom rules.

    Usage:
        storage = Storage()                        # default ~/.peekai/peekai.db
        storage = Storage("/tmp/test.db")          # custom path
        storage = Storage(capture_content=False)   # metadata-only mode
        storage = Storage(redact=False)            # disable redaction
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        capture_content: bool = True,
        redact: RedactOption = True,
    ) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.capture_content = capture_content
        self._redactor = build_redactor(redact)

        # Create the parent directory with owner-only permissions on POSIX.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            try:
                self.db_path.parent.chmod(0o700)
            except OSError:
                pass

        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # The connection is shared (check_same_thread=False) across the tracer,
        # CLI, and Streamlit's cached Storage. A single sqlite3 connection is not
        # safe for concurrent use, so serialise all access through this lock.
        self._lock = threading.RLock()
        self._migrate()
        # Harden db + WAL/SHM after the first write transaction so sidecar
        # files already exist when we chmod them.
        _harden_permissions(self.db_path)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(_CREATE_TRACES)
            self._conn.execute(_CREATE_SPANS)
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_trace_id ON spans(trace_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_spans_model ON spans(model)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_traces_started_at ON traces(started_at)"
            )

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def save_trace(self, trace: Trace) -> None:
        """Insert or replace a trace record."""
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO traces
                    (trace_id, name, started_at, ended_at, status,
                     total_input_tokens, total_output_tokens, total_tokens,
                     total_cost_usd, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.name,
                    _dt_to_str(trace.started_at),
                    _dt_to_str(trace.ended_at),
                    trace.status.value,
                    trace.total_input_tokens,
                    trace.total_output_tokens,
                    trace.total_tokens,
                    trace.total_cost_usd,
                    json.dumps(trace.metadata, default=str),
                ),
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        """Fetch a single trace with all its spans."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
            ).fetchone()
            if row is None:
                return None
            trace = self._row_to_trace(row)
            trace.spans = self.get_spans(trace_id)
        trace.span_count = len(trace.spans)
        return trace

    def list_traces(self, limit: int = 10) -> list[Trace]:
        """Return the most recent traces (with span counts but not spans)."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT t.*,
                    (SELECT COUNT(*) FROM spans s WHERE s.trace_id = t.trace_id)
                        AS span_count
                FROM traces t
                ORDER BY t.started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        traces = []
        for r in rows:
            trace = self._row_to_trace(r)
            trace.span_count = r["span_count"] or 0
            traces.append(trace)
        return traces

    def delete_all(self) -> None:
        """Wipe all traces and spans — used by `peekai clear`."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM spans")
            self._conn.execute("DELETE FROM traces")

    # ------------------------------------------------------------------
    # Spans
    # ------------------------------------------------------------------

    def save_span(self, span: Span) -> None:
        """Insert or replace a span record."""
        # 1. Redact secrets from raw content fields before any serialisation.
        #    Runs even when capture_content=True so secrets never reach the DB.
        if self._redactor is not None:
            input_data = self._redactor(span.input)
            output_data = self._redactor(span.output)
            raw_response_data = self._redactor(span.raw_response)
            tool_calls_data = self._redactor(span.tool_calls)
            error_data = self._redactor(span.error) if span.error is not None else None
        else:
            input_data = span.input
            output_data = span.output
            raw_response_data = span.raw_response
            tool_calls_data = span.tool_calls
            error_data = span.error

        # 2. When capture_content is disabled, blank all raw I/O after redaction.
        #    Timing, token counts, costs, status, and error_type are always kept.
        if self.capture_content:
            input_val = json.dumps(input_data, default=str)
            output_val = output_data if isinstance(output_data, str) else str(output_data)
            raw_response_val = json.dumps(raw_response_data, default=str)
            tool_calls_val = json.dumps(tool_calls_data, default=str)
            error_val = error_data
        else:
            input_val = "[]"
            output_val = ""
            raw_response_val = "{}"
            tool_calls_val = "[]"
            error_val = None  # drop message content, keep error_type

        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO spans
                    (span_id, trace_id, parent_span_id, name, kind, model, provider,
                     started_at, ended_at, status, input, output, raw_response,
                     input_tokens, output_tokens, total_tokens, cost_usd,
                     tool_calls, error, error_type, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    span.span_id,
                    span.trace_id,
                    span.parent_span_id,
                    span.name,
                    span.kind.value,
                    span.model,
                    span.provider,
                    _dt_to_str(span.started_at),
                    _dt_to_str(span.ended_at),
                    span.status.value,
                    input_val,
                    output_val,
                    raw_response_val,
                    span.input_tokens,
                    span.output_tokens,
                    span.total_tokens,
                    span.cost_usd,
                    tool_calls_val,
                    error_val,
                    span.error_type,
                    json.dumps(span.metadata, default=str),
                ),
            )

    def get_spans(self, trace_id: str) -> list[Span]:
        """Return all spans for a trace, ordered by start time."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM spans WHERE trace_id = ? ORDER BY started_at ASC",
                (trace_id,),
            ).fetchall()
        return [self._row_to_span(r) for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Aggregate stats across all traces."""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*)            AS total_runs,
                    SUM(total_tokens)   AS total_tokens,
                    SUM(total_cost_usd) AS total_cost_usd
                FROM traces
                WHERE status != 'pending'
                """
            ).fetchone()
        return {
            "total_runs": row["total_runs"] or 0,
            "total_tokens": row["total_tokens"] or 0,
            "total_cost_usd": row["total_cost_usd"] or 0.0,
        }

    def get_model_stats(self) -> list[dict[str, Any]]:
        """Aggregate token + cost stats grouped by model, queried directly from spans."""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    model,
                    provider,
                    COUNT(*)            AS calls,
                    SUM(total_tokens)   AS tokens,
                    SUM(cost_usd)       AS cost_usd
                FROM spans
                WHERE model != ''
                GROUP BY model, provider
                ORDER BY cost_usd DESC
                """
            ).fetchall()
        return [
            {
                "model": r["model"],
                "provider": r["provider"],
                "calls": r["calls"],
                "tokens": r["tokens"] or 0,
                "cost_usd": r["cost_usd"] or 0.0,
            }
            for r in rows
        ]

    def get_trace_ids_by_model(self, model: str) -> set[str]:
        """Get all trace IDs that contain spans using the specified model."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT trace_id FROM spans WHERE model = ?", (model,)
            ).fetchall()
        return {r["trace_id"] for r in rows}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _row_to_trace(self, row: sqlite3.Row) -> Trace:
        t = Trace(
            trace_id=row["trace_id"],
            name=row["name"],
            started_at=_str_to_dt(row["started_at"]) or datetime.now(timezone.utc),
            ended_at=_str_to_dt(row["ended_at"]),
            status=SpanStatus(row["status"]),
            total_input_tokens=row["total_input_tokens"],
            total_output_tokens=row["total_output_tokens"],
            total_tokens=row["total_tokens"],
            total_cost_usd=row["total_cost_usd"],
            metadata=json.loads(row["metadata"]),
        )
        return t

    def _row_to_span(self, row: sqlite3.Row) -> Span:
        return Span(
            span_id=row["span_id"],
            trace_id=row["trace_id"],
            parent_span_id=row["parent_span_id"],
            name=row["name"],
            kind=SpanKind(row["kind"]),
            model=row["model"],
            provider=row["provider"],
            started_at=_str_to_dt(row["started_at"]) or datetime.now(timezone.utc),
            ended_at=_str_to_dt(row["ended_at"]),
            status=SpanStatus(row["status"]),
            input=json.loads(row["input"]),
            output=row["output"],
            raw_response=json.loads(row["raw_response"]),
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            cost_usd=row["cost_usd"],
            tool_calls=json.loads(row["tool_calls"]),
            error=row["error"],
            error_type=row["error_type"],
            metadata=json.loads(row["metadata"]),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
