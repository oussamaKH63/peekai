"""
PeekAI multi-agent demo — shows parent/child span tree.

Run:
    uv run python examples/demo_multi_agent.py

Then inspect:
    uv run peekai map <trace-id>
    uv run peekai view <trace-id>
    uv run peekai ui
"""

from __future__ import annotations

import os
import peekai
from openai import OpenAI

API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = "gpt-4o-mini"

if not API_KEY:
    print("⚠️  OPENAI_API_KEY environment variable not set")
    print("   Please set it first:")
    print('   Windows: $env:OPENAI_API_KEY="your-key-here"')
    print('   Linux/Mac: export OPENAI_API_KEY="your-key-here"')
    exit(1)

os.environ["OPENAI_API_KEY"] = API_KEY
os.environ["OPENAI_BASE_URL"] = BASE_URL

peekai.init()
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ── Sub-agents ────────────────────────────────────────────────────────────────

@peekai.agent("researcher")
def researcher_agent(topic: str) -> str:
    """Researches a topic and returns a summary."""
    print(f"  [researcher] researching: {topic}")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a research assistant. Be concise, 2 sentences max."},
            {"role": "user",   "content": f"Give me 2 key facts about: {topic}"},
        ],
    )
    result = response.choices[0].message.content or ""
    print(f"  [researcher] → {result[:80]}…")
    return result


@peekai.agent("writer")
def writer_agent(research: str) -> str:
    """Takes research and writes a short summary."""
    print(f"  [writer] writing summary…")
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a writer. Write one punchy sentence."},
            {"role": "user",   "content": f"Summarise this research in one sentence: {research}"},
        ],
    )
    result = response.choices[0].message.content or ""
    print(f"  [writer] → {result}")
    return result


@peekai.tool("format_output")
def format_output(text: str) -> str:
    """Formats the final output."""
    return f"📝 {text.strip()}"


# ── Orchestrator ──────────────────────────────────────────────────────────────

@peekai.trace("multi_agent_pipeline")
def run_pipeline() -> None:
    print("\nRunning multi-agent pipeline…\n")

    # Step 1 — researcher agent
    research = researcher_agent("the James Webb Space Telescope")

    # Step 2 — writer agent uses researcher output
    summary = writer_agent(research)

    # Step 3 — tool formats the result
    output = format_output(summary)

    print(f"\nFinal output: {output}")
    print("\nDone! Now run:")
    print("  uv run peekai list")
    print("  uv run peekai map <trace-id>")
    print("  uv run peekai ui")


if __name__ == "__main__":
    run_pipeline()
