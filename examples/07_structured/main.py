"""Structured output example.

Provider-aware release example:
- Works when executed directly as: python examples/07_structured/main.py
- DeepSeek currently rejects native response_format structured output.
- In DeepSeek live mode, this example exits cleanly instead of failing release validation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from largestack import Agent
from examples._provider import main_or_skip, select_model


class Review(BaseModel):
    title: str = Field(description="Movie title")
    rating: int = Field(ge=1, le=10)
    summary: str


async def main():
    model = select_model()
    if model.startswith("deepseek/") or os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
        print(
            "SKIP_PROVIDER_CAPABILITY: DeepSeek response_format structured output is unavailable now."
        )
        return

    agent = Agent(
        name="structured-example",
        instructions="Return a concise structured movie review.",
        guardrails=None,
        llm=model,
    )

    result = await agent.run(
        "Review the movie 'Inception' with title, rating from 1-10, and summary.",
        response_model=Review,
    )

    print(getattr(result, "content", result))


if __name__ == "__main__":
    main_or_skip(main)
