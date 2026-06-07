"""Full production-style app: RAG + typed agent + tools."""

from pathlib import Path
import sys
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _provider import main_or_skip, select_model
from largestack import create_rag
from largestack.decorators import Agent, RunContext


@dataclass
class Deps:
    user_id: str


async def main():
    docs = ["Refund policy: 30 days money-back.", "Support: 24/7 for Enterprise."]
    rag = create_rag(documents=docs)
    agent = Agent[Deps, str](
        select_model(),
        deps_type=Deps,
        instructions="Search KB and answer concisely.",
    )

    @agent.tool
    async def search_kb(ctx: RunContext[Deps], query: str) -> str:
        """Search the knowledge base."""
        results = rag.retrieve(query, top_k=2)
        return "\n".join(str(r) for r in results)

    result = await agent.run("What's your refund policy?", deps=Deps(user_id="u1"))
    print(result.output)


if __name__ == "__main__":
    main_or_skip(main)
