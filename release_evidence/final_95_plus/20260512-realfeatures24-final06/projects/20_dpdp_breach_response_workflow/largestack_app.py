import asyncio
from largestack import Agent, Orchestrator, tool
from largestack.testing import TestModel


@tool
def lookup_policy(query: str) -> str:
    """Look up a policy by query."""
    return f"Policy for {query}: follow standard procedure."


async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: orchestrator_router and agent_tool_cost."""
    features = []
    evidence = {}

    # --- agent_tool_cost ---
    agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(
        model=TestModel(
            call_tools=["lookup_policy"],
            custom_tool_args={"lookup_policy": {"query": "refund"}}
        )
    ):
        result = await agent.run("Check refund policy")
    features.append("agent_tool_cost")
    evidence["agent_tool_calls"] = result.tool_calls_made
    evidence["agent_cost_budget"] = 0.1

    # --- orchestrator_router ---
    classifier = Agent(name="classifier", llm="deepseek/deepseek-chat", max_turns=1)
    specialist = Agent(name="billing", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"billing": specialist},
        default_route="billing"
    )
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch.run("route this")
    features.append("orchestrator_router")
    evidence["orchestrator_strategy"] = "router"
    evidence["route_output"] = route_result.output

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }


if __name__ == "__main__":
    asyncio.run(run_largestack_smoke())
