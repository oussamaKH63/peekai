# Changelog

All notable changes to PeekAI will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.5] — 2026-06-29

### Security
- Fix key-blind dict redaction gap — `_scrub_value` is now key-aware: when recursing a dict, values under sensitive keys (`api_key`, `password`, `token`, `secret`, `authorization`, `private_key`, `access_token`, `client_secret`, etc.) are replaced with `[REDACTED]` regardless of content shape. Previously only token-shaped secrets (matching a regex) were caught; plain-string passwords and custom-format tokens stored as dict values were not.
- Add PEM private/public key block pattern (`-----BEGIN ... KEY-----`).
- Redact `span.metadata` and `trace.metadata` before persistence (both were written raw).
- Remove redundant Anthropic key pattern (already matched by the `sk-` pattern).
- Remove dead `re.DOTALL` flag on the JSON-blob pattern.
- Short-circuit redaction when `capture_content=False` — no CPU wasted on data that will be discarded.
- Document known limitation: AWS 40-char secret access keys cannot be caught without false positives; real boundary is `0600` permissions.
- Expand test suite from 18 to 29 tests — new tests cover dict-form secrets, metadata redaction, raw DB bytes for dict secrets, capture_content short-circuit, and the AWS limitation.

---

## [0.1.4] — 2026-06-29

### Security
- Add redaction pipeline (`src/peekai/core/redaction.py`) — secrets are scrubbed from all span fields before persistence. Default patterns cover OpenAI keys (`sk-...`, `sk-proj-...`), Anthropic keys (`sk-ant-...`), AWS access key IDs (`AKIA...`), Bearer tokens, and common JSON secret fields (`api_key`, `password`, `access_token`, etc.).
- `peekai.init(redact=True)` — enabled by default. Pass `False` to disable, a `callable(str) -> str` for a custom scrubber, or a `list[re.Pattern]` for custom patterns.
- Redaction runs at the single chokepoint in `Storage.save_span`, before `capture_content` gating, so secrets never reach SQLite regardless of SDK or mode.
- 18 new tests in `tests/test_redaction.py` including a raw-DB-bytes assertion that the secret never reaches the file.

---

## [0.1.3] — 2026-06-29

### Security
- Trace directory (`~/.peekai/`) is now created with `0700` and the database plus WAL/SHM sidecar files are set to `0600` on POSIX systems (Linux/macOS), preventing other local users and indexing software from reading trace data. No-op on Windows (documented).
- Add `capture_content=False` option to `peekai.init()` and `Storage` — when disabled, raw prompts, completions, tool-call arguments, and error messages are blanked before persistence; token counts, costs, timings, model, and status are always retained.
- README: security warning block added near the storage section covering `.gitignore`, `peekai clear`, `capture_content=False`, and POSIX-only permission scope.

---

## [0.1.2] — 2026-06-21

### Added
- PyPI version badge and monthly downloads badge in README
- Full Anthropic `client.messages.stream()` context-manager support — sync and async — now produces traces identical to `create(stream=True)`

### Fixed
- License badge in README now links to the GitHub URL (was a relative path, broken on PyPI and some renderers)
- `pyproject.toml` license field changed to SPDX string format (`"MIT"`) — resolves the "unverified" license label on PyPI

---

## [0.1.1] — 2026-06-19

### Fixed
- README logo now renders correctly on PyPI
- Corrected GitHub repository URLs throughout (pyproject.toml, README, CONTRIBUTING, CHANGELOG)

---

## [0.1.0] — 2026-06-19

First public release.

### Added

**Core**
- `Trace` and `Span` dataclasses with full token, cost, and timing tracking
- `Tracer` with `ContextVar`-based async/thread safety for nested span trees
- SQLite storage at `~/.peekai/peekai.db` with WAL mode and indexed queries
- Token cost table for OpenAI and Anthropic models with LiteLLM fallback

**SDK patches** (auto-applied at `peekai.init()`)
- OpenAI — sync + async `chat.completions.create`, including `stream=True`
- Anthropic — sync + async `messages.create`, including `stream=True`
- LiteLLM — sync + async `completion`

**Decorators**
- `@peekai.trace("name")` — wraps a function as a top-level trace
- `@peekai.agent("name")` — wraps a sub-agent, LLM calls become children in the tree
- `@peekai.tool("name")` — wraps a tool call as a TOOL span

**CLI** (`peekai <command>`)
- `list` — show recent traces with status, tokens, cost, duration
- `view <id>` — full span waterfall with input/output/tool call detail
- `map <id>` — ASCII agent flow tree with nested parent/child spans
- `stats` — aggregate token + cost totals grouped by model
- `replay <id>` — re-run a trace with optional `--model` and `--tool` overrides
- `ui` — launch the Streamlit dashboard
- `clear` — wipe all local storage

**Web dashboard** (`peekai ui`)
- Dashboard page — KPIs, cost over time, per-model breakdown
- Traces page — filterable list with status, tokens, cost
- Trace view — span waterfall with duration bars, I/O tabs, error highlighting
- Replay page — side-by-side comparison with token/cost deltas

**Trace replay**
- Re-send stored prompts to any OpenAI-compatible or Anthropic model
- Inject modified tool responses via `--tool name=value`
- Replay saved as a new linked trace

---

[0.1.5]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.5
[0.1.4]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.4
[0.1.3]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.3
[0.1.2]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.2
[0.1.1]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.1
[0.1.0]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.0
