import json
import os
from largestack import Agent, create_rag
from largestack.testing import TestModel, capture_run_messages

async def run_largestack_smoke() -> dict:
    # Load fixture data
    fixture_path = os.path.join(os.path.dirname(__file__), 'data', 'partners_fixture.json')
    with open(fixture_path) as f:
        fixture = json.load(f)
    partner = fixture['partners'][0]

    # Feature: rag_citations
    documents = [
        "Duplicate payments occur when the same invoice is paid twice.",
        "Refund policy: all refunds must be approved by finance.",
        "Partner onboarding requires compliance attestation."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query='duplicate payments')
    search_tool = rag.as_tool()

    agent_rag = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        cost_budget=0.1,
        max_turns=2
    )

    with agent_rag.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result_rag = await agent_rag.run("Find information about duplicate payments.")

    rag_context = context
    rag_tool_calls = result_rag.tool_calls_made

    # Feature: observability_trace
    agent_obs = Agent(
        name="obs_agent",
        llm="deepseek/deepseek-chat",
        tools=[],
        cost_budget=0.1,
        max_turns=1
    )

    with capture_run_messages() as captured:
        with agent_obs.override(model=TestModel(custom_output_text="Observability check completed.", call_tools=[])):
            result_obs = await agent_obs.run("Run observability trace.")

    trace_id = result_obs.trace_id
    total_cost = result_obs.total_cost
    captured_messages = len(captured)
    # Redact any potential secret keys in captured messages
    redacted_log = []
    for msg in captured:
        content = str(msg)
        if 'sk-' in content:
            content = content.replace('sk-', '[REDACTED]')
        redacted_log.append(content)
    redacted_log_str = '\n'.join(redacted_log) if redacted_log else '[REDACTED] no secret keys present'

    return {
        "status": "ok",
        "features": ["rag_citations", "observability_trace"],
        "evidence": {
            "captured_messages": captured_messages,
            "rag_context": rag_context,
            "rag_tool_calls": rag_tool_calls,
            "redacted_log": redacted_log_str,
            "total_cost": total_cost,
            "trace_id": trace_id
        }
    }
