"""Streaming example.

Provider-aware release example:
- If Agent.run_stream exists, use streaming.
- Otherwise fall back to normal Agent.run.
- Works when executed directly as: python examples/06_streaming/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from largestack import Agent
from examples._provider import main_or_skip, select_model


async def main():
    agent = Agent(
        name="streaming-example",
        instructions="Answer clearly and briefly.",
        guardrails=None,
        llm=select_model(),
    )

    prompt = "Tell a 50-word story."

    if hasattr(agent, "run_stream"):
        async for chunk in agent.run_stream(prompt):
            print(chunk, end="", flush=True)
        print()
        return

    result = await agent.run(prompt)
    print("STREAMING_FALLBACK_NORMAL_RUN")
    print(getattr(result, "content", result))


if __name__ == "__main__":
    main_or_skip(main)
