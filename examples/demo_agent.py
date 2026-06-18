"""
PeekAI demo — real OpenAI-compatible API call.

Run:
    uv run python examples/demo_agent.py

Then inspect:
    uv run peekai list
    uv run peekai view <trace-id>
    uv run peekai ui
"""

from __future__ import annotations

import os
import peekai
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = "gpt-4o-mini"

if not API_KEY:
    from rich.console import Console
    console = Console()
    console.print()
    console.print("[bold yellow]⚠️  PeekAI Demo Setup[/bold yellow]")
    console.print("[dim]This demo requires an OpenAI API key.[/dim]")
    console.print()
    console.print("[bold]Quick setup:[/bold]")
    console.print("[dim]Windows PowerShell:[/dim]")
    console.print('  [green]$env:OPENAI_API_KEY="sk-your-key-here"[/green]')
    console.print("[dim]Linux/Mac:[/dim]")
    console.print('  [green]export OPENAI_API_KEY="sk-your-key-here"[/green]')
    console.print()
    console.print("[dim]Or create a .env file with: OPENAI_API_KEY=sk-...[/dim]")
    console.print()
    console.print("[dim]Get your API key at: https://platform.openai.com/api-keys[/dim]")
    console.print()
    exit(1)

# Automatically set env vars so replay engine and other tools can access them
os.environ["OPENAI_API_KEY"] = API_KEY
os.environ["OPENAI_BASE_URL"] = BASE_URL

# ── Init PeekAI ───────────────────────────────────────────────────────────────
peekai.init()

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# ── Agent ─────────────────────────────────────────────────────────────────────
@peekai.trace("demo_agent")
def run_agent() -> None:
    print("Running demo agent...\n")

    # Step 1 — simple question
    print("Step 1: asking a simple question")
    r1 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Be concise."},
            {"role": "user",   "content": "What is the capital of France?"},
        ],
    )
    answer1 = r1.choices[0].message.content
    print(f"  → {answer1}\n")

    # Step 2 — follow-up using the previous answer
    print("Step 2: follow-up question")
    r2 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system",    "content": "You are a helpful assistant. Be concise."},
            {"role": "user",      "content": "What is the capital of France?"},
            {"role": "assistant", "content": answer1 or ""},
            {"role": "user",      "content": "What is the population of that city?"},
        ],
    )
    answer2 = r2.choices[0].message.content
    print(f"  → {answer2}\n")

    # Step 3 — simulate a tool call span
    @peekai.tool("lookup_weather")
    def lookup_weather(city: str) -> str:
        # Fake tool — no real API call
        return f"Sunny, 22°C in {city}"

    weather = lookup_weather("Paris")
    print(f"Step 3: tool call → {weather}\n")

    # Step 4 — final summary using tool result
    print("Step 4: final summary")
    r3 = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant. Be concise."},
            {"role": "user",   "content": f"The weather in Paris is: {weather}. Write one sentence about visiting Paris today."},
        ],
    )
    answer3 = r3.choices[0].message.content
    print(f"  → {answer3}\n")

    print("Done! Now run:")
    print("  uv run peekai list")
    print("  uv run peekai stats")
    print("  uv run peekai ui")


if __name__ == "__main__":
    run_agent()
