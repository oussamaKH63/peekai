# 👀 PeekAI

**Lightweight, local-first observability and debugging for Python AI agents.**

No cloud. No API keys. No dashboards to sign up for. Just drop it in, call `peekai.init()`, and see exactly what your agent is doing.

---

## Why PeekAI?

Building AI agents is hard. Debugging them is harder. Most observability tools require you to send your data to their cloud, set up accounts, and configure pipelines before you can see a single trace.

PeekAI is different:

- **Local-first** — all traces stored in SQLite on your machine
- **Zero config** — one line to instrument OpenAI, Anthropic, and LiteLLM
- **Replay any trace** — re-run past agent calls with a different model or modified tool response
- **CLI + UI** — inspect traces in your terminal or a local Streamlit dashboard
- **Multi-agent aware** — visualize agent-to-agent handoffs as a span tree

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
# List recent traces
peekai list

# View a specific trace
peekai view <trace-id>

# See cost + token stats
peekai stats

# Launch the web UI
peekai ui
```

---

## Trace Replay

The killer feature. Re-run any past trace — swap the model, change a tool response, see what would have happened differently.

```bash
# Replay a trace with a different model
peekai replay <trace-id> --model claude-3-5-sonnet-20241022
```

---

## Roadmap

| Phase | Status |
|-------|--------|
| Core SDK (tracing + storage) | 🔵 In Progress |
| CLI | ⬜ Todo |
| Streamlit UI | ⬜ Todo |
| Trace Replay | ⬜ Todo |
| Multi-Agent Support | ⬜ Todo |
| v0.1 Public Release | ⬜ Todo |

---

## Contributing

Coming soon — see `CONTRIBUTING.md`.

---

## License

MIT
