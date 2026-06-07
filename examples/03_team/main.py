"""Multi-agent team using the configured provider."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent, Team


async def main():
    model = select_model()
    researcher = Agent(
        name="researcher",
        instructions="Find two concise facts.",
        llm=model,
        guardrails=False,
        cost_budget=0.08,
    )
    writer = Agent(
        name="writer",
        instructions="Write a one-sentence summary from the facts.",
        llm=model,
        guardrails=False,
        cost_budget=0.08,
    )
    team = Team(agents=[researcher, writer], strategy="sequential", cost_budget=0.20)
    try:
        result = await team.run("AI agent trends 2026", timeout=90)
        print(f"Output:\n{result.content}\nCost: ${result.total_cost:.4f}")
    finally:
        await close_quietly(team)


if __name__ == "__main__":
    main_or_skip(main, timeout=120)
