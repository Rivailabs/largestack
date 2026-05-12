"""Multi-agent research workflow example.

Demonstrates the Supervisor pattern with provider selection from environment.
The shared provider helper checks ``os.environ.get`` for DeepSeek/OpenAI keys
and exits cleanly when credentials are not configured.

Run::

    export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
    python multi_agent_research.py
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent
from largestack._core.multiagent import Supervisor


async def main():
    model = select_model()
    researcher = Agent(
        name="researcher",
        instructions=(
            "You research topics. Find specific facts, dates, numbers. "
            "Return structured findings, not prose."
        ),
        llm=model,
        guardrails=False,
        cost_budget=0.10,
    )
    writer = Agent(
        name="writer",
        instructions="Write clear prose from research findings. 200 words maximum.",
        llm=model,
        guardrails=False,
        cost_budget=0.10,
    )
    critic = Agent(
        name="critic",
        instructions="Critique writing briefly and specifically.",
        llm=model,
        guardrails=False,
        cost_budget=0.10,
    )
    supervisor_agent = Agent(
        name="supervisor",
        instructions="Coordinate specialist agents.",
        llm=model,
        guardrails=False,
        cost_budget=0.10,
    )
    sv = Supervisor(
        supervisor_agent=supervisor_agent,
        agents={"researcher": researcher, "writer": writer, "critic": critic},
        agent_descriptions={
            "researcher": "Gathers facts on a topic",
            "writer": "Composes prose from findings",
            "critic": "Reviews and critiques drafts",
        },
        max_iterations=5,
    )
    try:
        task = "Write a 150-word brief on the rise of agentic AI in 2025."
        print(f"Task: {task}\n")
        result = await sv.run(task)
        print("Final answer:")
        print(result.final_answer)
        print(f"Iterations: {result.iterations}")
    finally:
        for agent in (researcher, writer, critic, supervisor_agent):
            await close_quietly(agent)


if __name__ == "__main__":
    main_or_skip(main, timeout=120)
