# Contributing to PeekAI

Thanks for your interest in contributing. PeekAI is a small, focused tool — contributions that keep it simple and local-first are most welcome.

---

## Getting started

```bash
git clone https://github.com/oussamaKH63/peekai
cd peekai
uv sync --extra all
uv run pytest tests/ -v
```

That's it. No Docker, no external services, no environment variables needed to run the tests.

---

## Project structure

```
src/peekai/
├── __init__.py          # public API: init(), trace(), agent(), tool()
├── core/
│   ├── models.py        # Span, Trace dataclasses
│   ├── tracer.py        # Tracer with ContextVar async safety
│   ├── storage.py       # SQLite storage layer
│   └── costs.py         # Token cost table per model
├── patches/
│   ├── openai_patch.py  # OpenAI SDK monkey-patch
│   ├── anthropic_patch.py
│   └── litellm_patch.py
├── cli/
│   ├── main.py          # Typer app + command registration
│   ├── console.py       # Shared Rich console
│   └── commands/        # One file per CLI command
├── ui/
│   ├── app.py           # Streamlit dashboard
│   └── styles.py        # Inline HTML/CSS helpers
└── replay/
    └── engine.py        # Trace replay engine
```

---

## How to contribute

### Bug fixes
Open an issue first if it's non-trivial. For small fixes, a PR is fine directly.

### New features
Open an issue to discuss before building. PeekAI is intentionally minimal — features that add cloud dependencies, require external services, or significantly increase complexity are unlikely to be merged into v0.x.

### Adding a new SDK patch
1. Create `src/peekai/patches/<sdk>_patch.py`
2. Implement `patch(tracer)` and `unpatch()` following the existing pattern
3. Register it in `src/peekai/__init__.py` inside `init()`
4. Add a test in `tests/`

### Adding a model to the cost table
Edit `src/peekai/core/costs.py` — add the model name and `(input_per_1k, output_per_1k)` tuple. Include a source link in the PR description.

---

## Code style

- **Formatter**: `ruff format` (line length 88)
- **Linter**: `ruff check`
- **Types**: mypy strict — all public functions need type annotations

```bash
uv run ruff check src/
uv run ruff format src/
uv run mypy src/peekai/
```

---

## Tests

All tests live in `tests/`. Run them with:

```bash
uv run pytest tests/ -v
```

- Tests use `tmp_path` fixtures for SQLite — no shared state between tests
- No mocking of the OpenAI/Anthropic clients in unit tests — patches are tested via the tracer directly
- New features should include at least one test

---

## Pull request checklist

- [ ] Tests pass (`uv run pytest tests/ -v`)
- [ ] No new ruff errors (`uv run ruff check src/`)
- [ ] Type annotations on new public functions
- [ ] BACKLOG.md updated if a tracked task is completed

---

## Reporting issues

Include:
- Python version (`python --version`)
- PeekAI version (`peekai --version` or check `pyproject.toml`)
- Minimal reproduction script
- Full error traceback
