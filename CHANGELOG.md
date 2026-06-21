# Changelog

All notable changes to PeekAI will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.2]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.2
[0.1.1]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.1
[0.1.0]: https://github.com/oussamaKH63/peekai/releases/tag/v0.1.0
