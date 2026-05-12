"""Local LLM agent via Ollama (OpenAI-compatible endpoint).

Uses a locally-served Llama 3.1 model — no cloud API calls, zero cost, full
data residency. Great for India-DPDP deployments where data must stay on-prem.

Setup:
  ollama pull llama3.1:70b
  export LARGESTACK_OLLAMA_BASE_URL=http://localhost:11434/v1
  export # no API key needed for local Ollama
  python agent.py

If you don't have Ollama running, this falls back to TestModel for a smoke run.
"""
from __future__ import annotations
import asyncio
import os
import sys

from largestack import Agent, tool


@tool
def lookup_loan_status(loan_id: str) -> dict:
    """Look up the status of a loan by ID."""
    # In production: query your loan DB. Here: stub.
    return {"loan_id": loan_id, "status": "active",
            "balance_inr": 75000, "next_emi_due": "2026-06-05"}


def make_agent() -> Agent:
    # Point at local Ollama
    os.environ.setdefault("LARGESTACK_OLLAMA_BASE_URL", "http://localhost:11434")
    
    return Agent(
        name="local-loan-agent",
        instructions=(
            "You are a customer-support agent for an Indian NBFC. "
            "Use the lookup_loan_status tool to answer questions about loans. "
            "Reply concisely. Never reveal internal IDs to the customer."
        ),
        # Provider prefix is 'ollama' because this example uses the native LARGESTACK Ollama provider
        llm="ollama/llama3.1:70b",
        tools=[lookup_loan_status],
        cost_budget=0.01,    # local LLM = effectively free, but cap defensively
        max_turns=5,
    )


async def main():
    agent = make_agent()

    # If Ollama isn't running, fall back to TestModel so the example still smokes
    try:
        result = await agent.run("What's the status of loan L-12345?")
    except Exception as e:
        if "ConnectionError" in type(e).__name__ or "connect" in str(e).lower():
            print(f"[Ollama not reachable: {e}] — falling back to TestModel for smoke run\n")
            from largestack.testing import TestModel
            with agent.override(model=TestModel(call_tools=["lookup_loan_status"])):
                result = await agent.run("What's the status of loan L-12345?")
        else:
            raise

    print(f"Reply:        {result.content}")
    print(f"Trace ID:     {result.trace_id}")
    print(f"Tools used:   {result.tool_calls_made}")
    print(f"Turns:        {result.turns}")
    print(f"Duration ms:  {result.duration_ms:.1f}")
    print(f"Status:       {result.status}")


if __name__ == "__main__":
    asyncio.run(main())
