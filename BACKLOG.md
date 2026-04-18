# PeekAI — Product Backlog

> 👀 Lightweight, local-first observability and debugging for Python AI agents.

---

## How to use this backlog

- Keep this file in `docs/BACKLOG.md` inside your repo
- Use GitHub Projects as your weekly kanban board
- Every Sunday: pick tasks for the week and move them to "This Week"
- Update status here monthly as phases complete

**Status legend:** `⬜ Todo` `🔵 In Progress` `✅ Done`

---

## Phase 0 — Project Setup
> Goal: clean foundation before any real code

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ✅ | Set up project structure and folders | High | 30 min |
| ⬜ | Set up virtual environment | High | 15 min |
| ✅ | Create `pyproject.toml` with project metadata | High | 30 min |
| ✅ | Add `.gitignore` for Python + SQLite | High | 10 min |
| ✅ | Write initial README with vision + install preview | High | 45 min |

---

## Phase 1 — Core SDK (Instrumentation Layer)
> Goal: capture a real trace from a real OpenAI call

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ✅ | Create `Span` and `Trace` dataclasses | High | 1 hr |
| ✅ | Build `Tracer` class with `ContextVar` for async safety | High | 2 hrs |
| ✅ | Build `Storage` class with SQLite via `sqlite3` | High | 2 hrs |
| ✅ | Implement OpenAI SDK monkey-patch | High | 3 hrs |
| ✅ | Implement Anthropic SDK monkey-patch | High | 2 hrs |
| ✅ | Implement LiteLLM monkey-patch | Medium | 2 hrs |
| ✅ | Token tracking per span | High | 1 hr |
| ✅ | Cost calculation per span per model | High | 1 hr |
| ✅ | Error capture with full context | High | 1 hr |
| ✅ | `peekai.init()` auto-patches all installed SDKs | High | 1 hr |
| ✅ | `@peekai.trace()` decorator for agent runs | High | 1 hr |
| ✅ | Tool call tracking via decorator | Medium | 2 hrs |
| ✅ | Write unit tests for tracer and storage | Medium | 2 hrs |

---

## Phase 2 — CLI
> Goal: fully usable without any UI at all

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ✅ | Set up Typer CLI skeleton | High | 30 min |
| ✅ | `peekai list` — show last 10 traces | High | 1 hr |
| ✅ | `peekai view <trace-id>` — pretty print trace | High | 2 hrs |
| ✅ | `peekai stats` — total cost, tokens, runs | Medium | 1 hr |
| ✅ | `peekai clear` — wipe local storage | Medium | 30 min |
| ✅ | `peekai ui` — launch Streamlit UI | High | 30 min |
| ✅ | Colorized terminal output with `rich` | Medium | 1 hr |

---

## Phase 3 — Streamlit Web UI
> Goal: something you'd screenshot and post on Twitter

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ⬜ | Trace list view with status, cost, duration | High | 2 hrs |
| ⬜ | Trace detail waterfall view (span by span) | High | 3 hrs |
| ⬜ | Token + cost breakdown per span | High | 1 hr |
| ⬜ | Error highlighting in trace view | High | 1 hr |
| ⬜ | Filter traces by status, model, date | Medium | 2 hrs |
| ⬜ | JSON input/output viewer per span | Medium | 1 hr |
| ⬜ | Total dashboard — runs, cost, tokens over time | Medium | 2 hrs |

---

## Phase 4 — Trace Replay (Differentiator)
> Goal: re-run any past trace — the killer feature

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ⬜ | Store full prompt + response per span in SQLite | High | 1 hr |
| ⬜ | `peekai replay <trace-id>` CLI command | High | 3 hrs |
| ⬜ | Replay with model swap (GPT-4o vs Claude) | High | 3 hrs |
| ⬜ | Replay with modified tool response | Medium | 4 hrs |
| ⬜ | Side by side original vs replayed trace in UI | Medium | 3 hrs |

---

## Phase 5 — Multi-Agent Support
> Goal: visualize agent-to-agent calls

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ⬜ | Parent/child span relationship in data model | High | 2 hrs |
| ⬜ | Agent handoff tracking via context propagation | High | 3 hrs |
| ⬜ | Multi-agent waterfall tree view in UI | High | 4 hrs |
| ⬜ | `peekai map <trace-id>` — ASCII agent flow in CLI | Medium | 2 hrs |

---

## Phase 6 — Polish + Ship v0.1
> Goal: public release, real people using it

| Status | Task | Priority | Effort |
|--------|------|----------|--------|
| ⬜ | Write proper README with badges + demo gif | High | 2 hrs |
| ⬜ | Record demo gif with a real agent example | High | 1 hr |
| ⬜ | Write `CONTRIBUTING.md` | Medium | 1 hr |
| ⬜ | Publish to PyPI | High | 1 hr |
| ⬜ | Post on HackerNews — Show HN | High | 30 min |
| ⬜ | Post on Reddit r/LocalLLaMA + r/Python | High | 30 min |
| ⬜ | Post demo gif on X/Twitter | High | 15 min |

---

## V2 Backlog — Do not touch until real users ask
> Ideas for after v0.1 is live and people are using it

- [ ] Eval hooks — attach pass/fail criteria to a trace
- [ ] Failure clustering — group similar errors across runs automatically
- [ ] Agent diff — compare two runs side by side
- [ ] Export to Langfuse / OpenTelemetry format
- [ ] VS Code extension
- [ ] GitHub Action for CI agent testing
- [ ] Async agent support improvements
- [ ] Custom span types for domain-specific agents

---

## Weekly Routine

```
Sunday evening (15 min):
  → Review Done column
  → Pick next week tasks from Backlog
  → Move to "This Week" on GitHub Projects

Weekday evenings (1.5 hrs):
  → 15 min: review board, pick one task
  → 60 min: build only
  → 15 min: commit, update board, note where you stopped

Weekend (4-5 hrs/day):
  → Bigger tasks, integrations, UI work
```

---

*Last updated: April 2026*
