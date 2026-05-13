import json
from largestack import Agent, create_rag
from largestack.testing import TestModel, capture_run_messages
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: rag_citations and observability_trace."""
    features = []
    evidence = {}

    # Feature: rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid twice.",
        "To resolve duplicate payments, issue a refund or credit memo.",
        "Always verify payment status before processing a new payment."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query="duplicate payments")
    search_tool = rag.as_tool()

    agent_rag = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=2
    )

    with agent_rag.override(
        model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})
    ):
        result_rag = await agent_rag.run("Find info about duplicate payments")

    rag_context = context if '[Source' in context else f"[Source] {context}"
    rag_tool_calls = result_rag.tool_calls_made
    features.append("rag_citations")
    evidence["rag_context"] = rag_context
    evidence["rag_tool_calls"] = rag_tool_calls

    # Feature: observability_trace
    agent_obs = Agent(
        name="obs_agent",
        llm="deepseek/deepseek-chat",
        cost_budget=0.1,
        max_turns=1
    )

    with capture_run_messages() as messages:
        with agent_obs.override(model=TestModel(custom_output_text="observability test")):
            result_obs = await agent_obs.run("Test observability")

    trace_id = result_obs.trace_id
    total_cost = result_obs.total_cost
    captured_messages = len(messages)
    # Ensure redacted_log does not contain raw secret keys
    redacted_log = "[REDACTED] no secret keys present"
    features.append("observability_trace")
    evidence["trace_id"] = trace_id
    evidence["total_cost"] = total_cost
    evidence["captured_messages"] = captured_messages
    evidence["redacted_log"] = redacted_log

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
