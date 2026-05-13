"""Real LARGESTACK smoke for the AML transaction monitoring project."""
from __future__ import annotations

from largestack import Agent, Orchestrator, create_rag
from largestack.testing import TestModel, capture_run_messages


async def run_largestack_smoke() -> dict:
    """Execute router orchestration, RAG citations, and observability locally."""
    features: list[str] = []
    evidence: dict = {}

    classifier = Agent(name="aml-classifier", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    investigator = Agent(name="aml-investigator", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    orchestrator = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"investigate": investigator},
        default_route="investigate",
    )
    with classifier.override(model=TestModel("investigate")), investigator.override(model=TestModel("route ok")):
        route_result = await orchestrator.run("route sanctioned crypto mixer alert")
    features.append("orchestrator_router")
    evidence["orchestrator_strategy"] = "router"
    evidence["route_output"] = route_result.output

    docs = [
        "High risk sanctions or structuring cases require MLRO review before filing SAR.",
        "Cash structuring and crypto mixer payouts require enhanced due diligence.",
    ]
    rag = create_rag(documents=docs, chunk_size=120, top_k=2)
    context = rag.build_context(query="sanctions sar filing")
    rag_agent = Agent(
        name="aml-rag-agent",
        llm="deepseek/deepseek-chat",
        tools=[rag.as_tool()],
        max_turns=1,
        cost_budget=0.1,
    )
    with rag_agent.override(
        model=TestModel(
            call_tools=["search_knowledge"],
            custom_tool_args={"search_knowledge": {"query": "sanctions sar filing"}},
        )
    ):
        rag_result = await rag_agent.run("Find AML policy evidence")
    features.append("rag_citations")
    evidence["rag_context"] = context
    evidence["rag_tool_calls"] = rag_result.tool_calls_made

    trace_agent = Agent(name="aml-trace-agent", llm="deepseek/deepseek-chat", max_turns=1, cost_budget=0.1)
    with capture_run_messages() as captured:
        with trace_agent.override(model=TestModel("trace ok")):
            trace_result = await trace_agent.run("trace AML alert")
    features.append("observability_trace")
    evidence["trace_id"] = trace_result.trace_id
    evidence["captured_messages"] = len(captured)
    evidence["total_cost"] = trace_result.total_cost
    evidence["redacted_log"] = "[REDACTED] synthetic AML validation run"

    return {"status": "ok", "features": features, "evidence": evidence}
