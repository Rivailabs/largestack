"""Hello World using the configured provider."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent


async def main():
    agent = Agent(
        name="hello",
        instructions="Keep responses brief.",
        llm=select_model(),
        guardrails=False,
        cost_budget=0.10,
    )
    try:
        result = await agent.run("What is the meaning of life? One sentence.", timeout=90)
        print(f"Agent: {result.content}\nCost: ${result.total_cost:.4f}")
    finally:
        await close_quietly(agent)


if __name__ == "__main__":
    main_or_skip(main)
