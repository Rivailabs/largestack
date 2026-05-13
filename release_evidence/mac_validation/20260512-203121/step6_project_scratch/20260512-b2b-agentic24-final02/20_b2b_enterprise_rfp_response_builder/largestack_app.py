import asyncio
from largestack import Agent, Orchestrator, tool
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up a policy by query string."""
    # Simulated policy lookup
    policies = {
        "refund": "Refund policy: Full refund within 30 days.",
        "privacy": "Privacy policy: We do not share your data.",
    }
    return policies.get(query.lower(), "Policy not found.")

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features: orchestrator_router and agent_tool_cost."""
    # Feature: agent_tool_cost
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
        result = await agent.run("What is the refund policy?")
    agent_tool_calls = result.tool_calls_made
    agent_cost_budget = agent.cost_budget

    # Feature: orchestrator_router
    classifier = Agent(name="classifier", llm="deepseek/deepseek-chat")
    specialist = Agent(name="billing", llm="deepseek/deepseek-chat")
    orch = Orchestrator(
        strategy="router",
        classifier=classifier,
        routes={"billing": specialist},
        default_route="billing"
    )
    with classifier.override(model=TestModel("billing")), specialist.override(model=TestModel("routed ok")):
        route_result = await orch.run("route this")
    route_output = route_result.output
    orchestrator_strategy = "router"

    return {
        "status": "ok",
        "features": ["orchestrator_router", "agent_tool_cost"],
        "evidence": {
            "agent_cost_budget": agent_cost_budget,
            "agent_tool_calls": agent_tool_calls,
            "orchestrator_strategy": orchestrator_strategy,
            "route_output": route_output
        }
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
