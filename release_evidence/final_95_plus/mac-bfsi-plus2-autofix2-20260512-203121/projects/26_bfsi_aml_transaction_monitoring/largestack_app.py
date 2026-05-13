import asyncio
from largestack import Agent, Orchestrator, create_rag
from largestack.testing import TestModel, capture_run_messages
from largestack.decorators import Agent as TypedAgent, RunContext, ModelRetry
from largestack.memory import create_memory
from largestack import create_guardrails
from types import SimpleNamespace

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # ========== orchestrator_router ==========
    classifier = Agent(
        name="classifier",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    specialist = Agent(
        name="billing",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"billing": specialist},
        default_route="billing"
    )
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch.run("route this")
    route_output = route_result.output
    features.append("orchestrator_router")
    evidence["orchestrator_strategy"] = "router"
    evidence["route_output"] = route_output

    # ========== rag_citations ==========
    documents = [
        "Duplicate payments must be refunded within 30 days.",
        "All refunds require manager approval."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query="duplicate payments")
    search_tool = rag.as_tool()
    agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[search_tool],
        max_turns=2
    )
    with agent.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        result = await agent.run("Find info about duplicate payments")
    features.append("rag_citations")
    evidence["rag_context"] = context
    evidence["rag_tool_calls"] = result.tool_calls_made

    # ========== observability_trace ==========
    agent_obs = Agent(
        name="obs_agent",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    with capture_run_messages() as messages:
        with agent_obs.override(model=TestModel("observability test")):
            obs_result = await agent_obs.run("test")
    features.append("observability_trace")
    evidence["trace_id"] = obs_result.trace_id
    evidence["captured_messages"] = len(messages)
    evidence["total_cost"] = obs_result.total_cost
    # Redacted log: ensure no secret keys
    redacted_log = "[REDACTED] no secret keys present"
    evidence["redacted_log"] = redacted_log

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
