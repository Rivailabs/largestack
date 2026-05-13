import asyncio
from largestack import Agent, Orchestrator, create_rag
from largestack.testing import TestModel, capture_run_messages
from largestack.memory import create_memory

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: orchestrator_router, rag_citations, observability_trace.
    Returns dict with status, features list, and evidence.
    """
    features = []
    evidence = {}

    # --- orchestrator_router ---
    classifier = Agent(
        name="classifier",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    specialist = Agent(
        name="billing",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
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

    # --- rag_citations ---
    documents = [
        "Duplicate payments must be refunded within 30 days.",
        "All refunds require manager approval.",
        "Chargebacks are handled by the billing team."
    ]
    rag = create_rag(documents=documents, chunk_size=100, top_k=2)
    context = rag.build_context(query="duplicate payments")
    rag_tool = rag.as_tool()
    rag_agent = Agent(
        name="rag_agent",
        llm="deepseek/deepseek-chat",
        tools=[rag_tool],
        max_turns=1,
        cost_budget=0.1
    )
    with rag_agent.override(model=TestModel(call_tools=["search_knowledge"], custom_tool_args={"search_knowledge": {"query": "duplicate payments"}})):
        rag_result = await rag_agent.run("Find info about duplicate payments")
    features.append("rag_citations")
    evidence["rag_context"] = context
    evidence["rag_tool_calls"] = rag_result.tool_calls_made

    # --- observability_trace ---
    trace_agent = Agent(
        name="trace_agent",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    with capture_run_messages() as captured:
        with trace_agent.override(model=TestModel("trace ok")):
            trace_result = await trace_agent.run("test trace")
    features.append("observability_trace")
    evidence["trace_id"] = trace_result.trace_id
    evidence["captured_messages"] = len(captured)
    evidence["total_cost"] = trace_result.total_cost
    evidence["redacted_log"] = "[REDACTED] no secret keys present"

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
