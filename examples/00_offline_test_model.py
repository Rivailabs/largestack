"""Offline quickstart: runs without provider keys or network."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
from largestack import Agent
from largestack.testing import TestModel


async def main():
    agent = Agent(
        name="offline",
        instructions="Reply briefly.",
        llm="deepseek/deepseek-chat",
        guardrails=False,
    )
    model = TestModel(custom_output_text="Offline TestModel response: agent flow works.")
    with agent.override(model=model):
        result = await agent.run("Hello offline agent")
    print(result.content)
    print(f"Model calls: {model.calls}")


if __name__ == "__main__":
    asyncio.run(main())
