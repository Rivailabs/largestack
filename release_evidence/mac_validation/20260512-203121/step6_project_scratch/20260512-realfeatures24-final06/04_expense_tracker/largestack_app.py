import asyncio
from types import SimpleNamespace

from largestack import Agent, create_rag
from largestack.testing import TestModel
from largestack import create_guardrails


async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # Feature: rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid twice.",
        "Always verify invoice numbers before processing payments.",
        "Refund requests should be reviewed by the finance team."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query="duplicate payments")
    rag_tool = rag.as_tool()

    agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[rag_tool],
        cost_budget=0.1,
        max_turns=3
    )

    with agent.override(
        model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})
    ):
        result = await agent.run("Find information about duplicate payments")

    rag_context = context
    rag_tool_calls = result.tool_calls_made
    features.append("rag_citations")
    evidence["rag_context"] = rag_context
    evidence["rag_tool_calls"] = rag_tool_calls

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
    response = SimpleNamespace(content="Contact me at test@example.com for details.")
    await guardrails.check_output(response)
    redacted_text = response.content
    features.append("guardrails_pii")
    evidence["redacted_text"] = redacted_text

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }


if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
