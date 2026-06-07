"""RAG/tool-backed knowledge example using the configured provider."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent, tool

KB = {
    "pricing": "Largestack AI Professional costs $299/year.",
    "features": "Tracing, cost control, guardrails, MCP, and RAG are supported.",
}


@tool
async def search_kb(query: str) -> str:
    """Search the small example knowledge base."""
    q = query.lower()
    hits = [
        value
        for key, value in KB.items()
        if key in q or any(word in value.lower() for word in q.split())
    ]
    return "\n".join(hits) if hits else "Not found."


async def main():
    agent = Agent(
        name="kb",
        instructions="Use search_kb before answering. Include exact prices when found.",
        tools=[search_kb],
        llm=select_model(),
        guardrails=False,
        cost_budget=0.10,
        max_turns=5,
    )
    try:
        result = await agent.run("How much does LARGESTACK Professional cost?", timeout=90)
        print(f"Answer: {result.content}")
    finally:
        await close_quietly(agent)


if __name__ == "__main__":
    main_or_skip(main)
