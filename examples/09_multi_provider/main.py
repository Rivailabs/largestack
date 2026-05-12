"""Provider fallback example using configured provider keys."""
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent


def fallback_model(primary: str) -> str:
    if primary.startswith("deepseek/") and os.environ.get("LARGESTACK_OPENAI_API_KEY"):
        return "openai/gpt-4o-mini"
    if primary.startswith("openai/") and os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
        return "deepseek/deepseek-chat"
    return primary


async def main():
    primary_model = select_model()
    fallback = Agent(name="fallback", llm=fallback_model(primary_model), guardrails=False, cost_budget=0.10)
    primary = Agent(name="primary", llm=primary_model, fallback=fallback, guardrails=False, cost_budget=0.10)
    try:
        result = await primary.run("What is Python? Answer in one sentence.", timeout=90)
        print(result.content)
    finally:
        await close_quietly(primary)
        await close_quietly(fallback)


if __name__ == "__main__":
    main_or_skip(main)
