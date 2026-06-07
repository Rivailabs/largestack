"""Chat-only local LLM agent (no tools).

Smaller Ollama models (e.g. llama3.1:8b) are unreliable at tool calling but
fine for plain chat / RAG. Use this variant when:

- You're running on consumer hardware (16-32 GB RAM)
- Your agent doesn't need tool calls — just conversation, summarisation, RAG

Setup:
  ollama pull llama3.1:8b
  export LARGESTACK_OLLAMA_BASE_URL=http://localhost:11434/v1
  export # no API key needed for local Ollama
  python chat_only.py
"""

from __future__ import annotations
import asyncio
import os

from largestack import Agent


async def main():
    os.environ.setdefault("LARGESTACK_OLLAMA_BASE_URL", "http://localhost:11434")

    agent = Agent(
        name="local-chat",
        instructions="You are a concise assistant. Reply in 1-3 sentences.",
        llm="ollama/llama3.1:8b",
        cost_budget=0.0,
        max_turns=3,
    )

    try:
        result = await agent.run("Explain the DPDP Act 2023 in one paragraph.")
        print(result.content)
    except Exception as e:
        if "connect" in str(e).lower():
            print(f"[Ollama not reachable: {e}] — start Ollama with `ollama serve`")
        else:
            raise


if __name__ == "__main__":
    asyncio.run(main())
