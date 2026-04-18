"""
SQLite-backed local storage for traces and spans.

Schema
------
traces  — one row per Trace
spans   — one row per Span, foreign-keyed to traces
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from peekai.core.models import Span, SpanKind, SpanStatus, Trace

_DEFAULT_DB_PATH = Path.home() / ".peekai" / "peekai.db"

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

    Usage:
        storage = Storage()                        # default ~/.peekai/peekai.db
        storage = Storage("/tmp/test.db")          # custom path
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_TRACES)
            self._conn.execute(_CREATE_SPANS)

    # ------------------------------------------------------------------
    # Traces
    # ------------------------------------------------------------------

    def save_trace(self, trace: Trace) -> None:
        """Insert or replace a trace record."""
        with self._conn:
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
                    json.dumps(trace.metadata),
                ),
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        """Fetch a single trace with all its spans."""
        row = self._conn.execute(
            "SELECT * FROM traces WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        if row is None:
            return None
        trace = self._row_to_trace(row)
        trace.spans = self.get_spans(trace_id)
        return trace

    def list_traces(self, limit: int = 10) -> list[Trace]:
        """Return the most recent traces (without spans for performance)."""
        rows = self._conn.execute(
            "SELECT * FROM traces ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_trace(r) for r in rows]

    def delete_all(self) -> None:
        """Wipe all traces and spans — used by `peekai clear`."""
        with self._conn:
            self._conn.execute("DELETE FROM spans")
            self._conn.execute("DELETE FROM traces")

    # ------------------------------------------------------------------
    # Spans
    # ------------------------------------------------------------------

    def save_span(self, span: Span) -> None:
        """Insert or replace a span record."""
        with self._conn:
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
                    json.dumps(span.input),
                    span.output,
                    json.dumps(span.raw_response),
                    span.input_tokens,
                    span.output_tokens,
                    span.total_tokens,
                    span.cost_usd,
                    json.dumps(span.tool_calls),
                    span.error,
                    span.error_type,
                    json.dumps(span.metadata),
                ),
            )

    def get_spans(self, trace_id: str) -> list[Span]:
        """Return all spans for a trace, ordered by start time."""
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
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
