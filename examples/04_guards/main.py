"""Guardrails example using the configured provider."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import close_quietly, main_or_skip, select_model
from largestack import Agent, Guardrails
from largestack._guard.injection import InjectionGuard
from largestack._guard.pii import PIIGuard


async def main():
    guardrails = Guardrails(guards=[PIIGuard(action="warn"), InjectionGuard()])
    agent = Agent(name="safe", instructions="Answer briefly and safely.", guardrails=guardrails, llm=select_model(), cost_budget=0.10)
    try:
        result = await agent.run("What is machine learning?", timeout=90)
        print(f"Result: {result.content[:300]}")
    finally:
        await close_quietly(agent)


if __name__ == "__main__":
    main_or_skip(main)
