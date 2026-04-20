# 👀 PeekAI

**Lightweight, local-first observability and debugging for Python AI agents.**

No cloud. No API keys. No dashboards to sign up for. Drop it in, call `peekai.init()`, and see exactly what your agent is doing — every LLM call, every tool use, every token spent.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)](https://github.com/peekai/peekai)

---

## Why PeekAI?

Building AI agents is hard. Debugging them is harder. Most observability tools require you to send your data to their cloud, set up accounts, and configure pipelines before you can see a single trace.

PeekAI is different:

- **Local-first** — all traces stored in SQLite on your machine, nothing leaves your environment
- **Zero config** — one line to instrument OpenAI, Anthropic, and LiteLLM
- **Multi-agent aware** — visualize agent-to-agent handoffs as a nested span tree
- **Trace replay** — re-run any past trace with a different model or modified tool response
- **CLI + UI** — inspect traces in your terminal or a local Streamlit dashboard

---

## Install

```bash
pip install peekai

# With OpenAI support
pip install "peekai[openai]"

# With all SDK support
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

## Supported SDKs

| SDK | Status |
|---|---|
| OpenAI | ✅ Auto-patched |
| Anthropic | ✅ Auto-patched |
| LiteLLM | ✅ Auto-patched |

All patching happens at `peekai.init()` — no changes to your existing code.

---

## Development

```bash
# Clone and install
git clone https://github.com/peekai/peekai
cd peekai
uv sync --extra all

# Run tests
uv run pytest tests/ -v

# Run the demo
uv run python examples/demo_agent.py
uv run python examples/demo_multi_agent.py

# Launch the UI
uv run peekai ui
```

---

## Roadmap

| Phase | Status |
|---|---|
| Core SDK — tracing, storage, patches | ✅ Done |
| CLI — list, view, stats, clear, map | ✅ Done |
| Streamlit UI — dashboard, traces, waterfall | ✅ Done |
| Trace Replay — model swap, tool override | ✅ Done |
| Multi-Agent — nested spans, agent decorator | ✅ Done |
| v0.1 Public Release | 🔵 In Progress |

---

## Contributing

See `CONTRIBUTING.md` — coming soon.

---

## License

MIT
