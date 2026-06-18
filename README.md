<div align="center">
  <img src="https://raw.githubusercontent.com/peekai/peekai/main/peekai-name-logo.png" alt="PeekAI" width="320" />

  <p><strong>Lightweight, local-first observability and debugging for Python AI agents.</strong></p>

  <p>No cloud. No API keys. No dashboards to sign up for.<br/>
  Drop it in, call <code>peekai.init()</code>, and see exactly what your agent is doing —<br/>
  every LLM call, every tool use, every token spent.</p>

  [![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
  [![Status](https://img.shields.io/badge/status-alpha-orange)](https://github.com/peekai/peekai)
  [![uv](https://img.shields.io/badge/packaged%20with-uv-purple)](https://github.com/astral-sh/uv)
</div>

---

## Why PeekAI?

Building AI agents is hard. Debugging them is harder. Tools like LangSmith or Weights & Biases require you to send your data to their cloud, create accounts, and wire up pipelines before you can see a single trace.

PeekAI is different:

| | |
|---|---|
| 🏠 **Local-first** | All traces stored in SQLite at `~/.peekai/peekai.db` — nothing leaves your machine |
| ⚡ **Zero config** | One line to instrument OpenAI, Anthropic, and LiteLLM |
| 🧠 **Multi-agent aware** | Visualize agent-to-agent handoffs as a nested span tree |
| 🔁 **Trace replay** | Re-run any past trace with a different model or modified tool response |
| 🖥️ **CLI + UI** | Inspect traces in your terminal or a local Streamlit dashboard |

---

## Install

```bash
pip install peekai

# With OpenAI support
pip install "peekai[openai]"

# With Anthropic support
pip install "peekai[anthropic]"

# With the web dashboard
pip install "peekai[ui]"

# With everything
pip install "peekai[all]"
```

---

## Quickstart

```python
import peekai
from openai import OpenAI

# One line to instrument everything
peekai.init()

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is 2 + 2?"}],
)

print(response.choices[0].message.content)
```

Then inspect your traces:

```bash
peekai list                  # recent traces
peekai view <trace-id>       # full span waterfall
peekai stats                 # token + cost totals
peekai ui                    # launch the web dashboard
```

> **How it works** — `peekai.init()` monkey-patches the SDK clients at startup. No changes to your existing API calls are needed.

---

## Multi-Agent Support

Decorate your agents and tools — PeekAI automatically builds the parent/child span tree:

```python
import peekai
from openai import OpenAI

peekai.init()
client = OpenAI()


@peekai.agent("researcher")
def researcher_agent(topic: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Research: {topic}"}],
    )
    return response.choices[0].message.content


@peekai.agent("writer")
def writer_agent(research: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": f"Summarise: {research}"}],
    )
    return response.choices[0].message.content


@peekai.tool("format_output")
def format_output(text: str) -> str:
    return f"📝 {text}"


@peekai.trace("multi_agent_pipeline")
def run():
    research = researcher_agent("the James Webb Space Telescope")
    summary = writer_agent(research)
    return format_output(summary)


run()
```

Visualize the agent flow in the terminal:

```bash
peekai map <trace-id>
```

```
  trace: multi_agent_pipeline  ✓ ok  3.6s  236 tokens  $0.000222

  └── 🧠 researcher  [agent]  ✓ ok  2.3s
      └── 🤖 openai/gpt-4o  [llm]  ✓ ok  2.3s  102 tok  $0.000115
  └── 🧠 writer  [agent]  ✓ ok  1.3s
      └── 🤖 openai/gpt-4o  [llm]  ✓ ok  1.3s  134 tok  $0.000107
  └── 🔧 format_output  [tool]  ✓ ok  0ms
```

---

## Trace Replay

Re-run any past trace — swap the model, inject a different tool response, see what would have changed:

```bash
# Replay with the same model
peekai replay <trace-id>

# Swap to a different model
peekai replay <trace-id> --model gpt-4o

# Swap to Anthropic
peekai replay <trace-id> --model claude-3-5-sonnet-20241022

# Inject a modified tool response
peekai replay <trace-id> --tool search="different search result"
```

The replay is saved as a new trace and shown side by side in the UI with token/cost deltas.

---

## CLI Reference

| Command | Description |
|---|---|
| `peekai list` | Show last 10 traces |
| `peekai view <id>` | Full span waterfall with I/O |
| `peekai stats` | Total runs, tokens, cost by model |
| `peekai map <id>` | ASCII agent flow tree |
| `peekai replay <id>` | Re-run a trace (supports `--model`, `--tool`) |
| `peekai ui` | Launch Streamlit dashboard |
| `peekai clear` | Wipe local storage |

All commands accept short trace IDs — the first 8 characters are enough.

---

## Web Dashboard

```bash
peekai ui
```

Opens at `http://localhost:8501` with four pages:

- **Dashboard** — KPIs, cost over time, per-model breakdown
- **Traces** — filterable list with status, tokens, cost
- **Trace View** — span waterfall with duration bars, input/output tabs, error highlighting
- **Replay** — run a replay with model swap, side-by-side comparison

---

## Decorators

| Decorator | What it does |
|---|---|
| `@peekai.trace("name")` | Wraps a function as a top-level trace |
| `@peekai.agent("name")` | Wraps a sub-agent — its LLM calls become children in the tree |
| `@peekai.tool("name")` | Wraps a tool call as a TOOL span |

---

## `peekai.init()` options

```python
peekai.init(
    db_path="./my_traces.db",  # default: ~/.peekai/peekai.db
    openai=True,               # patch OpenAI SDK (default True)
    anthropic=True,            # patch Anthropic SDK (default True)
    litellm=True,              # patch LiteLLM (default True)
)
```

Traces are stored locally at `~/.peekai/peekai.db` by default. You can open it directly with any SQLite viewer, back it up, or wipe it with `peekai clear`.

---

## Supported SDKs

| SDK | Status | Notes |
|---|---|---|
| OpenAI | ✅ Auto-patched | sync + async, streaming |
| Anthropic | ✅ Auto-patched | sync + async, `create(stream=True)` |
| LiteLLM | ✅ Auto-patched | sync + async |

> **Note** — the Anthropic `client.messages.stream()` context manager helper is not currently patched. Use `client.messages.create(stream=True)` to get streaming traces.

---

## Development

```bash
# Clone and install
git clone https://github.com/peekai/peekai
cd peekai
uv sync --extra all  # includes openai, anthropic, litellm, ui

# Run tests
uv run pytest tests/ -v

# Run the demos
uv run python examples/demo_agent.py
uv run python examples/demo_multi_agent.py

# Launch the UI
uv run peekai ui
```

---

## Roadmap

| Feature | Status |
|---|---|
| Core SDK — tracing, storage, patches | ✅ Done |
| CLI — list, view, stats, clear, map | ✅ Done |
| Streamlit UI — dashboard, traces, waterfall | ✅ Done |
| Trace Replay — model swap, tool override | ✅ Done |
| Multi-Agent — nested spans, agent decorator | ✅ Done |
| v0.1 Public Release | 🔵 In Progress |

---

## Contributing

```bash
# Install dev dependencies
uv sync --extra dev

# Run linter
uv run ruff check src/

# Run type checker
uv run mypy src/

# Run tests
uv run pytest tests/ -v
```

PRs and issues are welcome. See `CONTRIBUTING.md` for more detail.

---

## License

MIT © [Oussema Khorchani](https://github.com/peekai)
