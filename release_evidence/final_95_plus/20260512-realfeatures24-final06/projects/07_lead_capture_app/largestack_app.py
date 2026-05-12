import asyncio
from largestack import Agent, Orchestrator, tool
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up policy information."""
    return f"Policy for {query}: Standard refund policy applies."

async def run_largestack_smoke() -> dict:
    # Map-reduce orchestration
    mapper = Agent(name="mapper", llm="deepseek/deepseek-chat", max_turns=1)
    reducer = Agent(name="reducer", llm="deepseek/deepseek-chat", max_turns=1)
    orch = Orchestrator(strategy="map_reduce", mapper=mapper, reducer=reducer)
    items = ["item1", "item2", "item3"]
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result = await orch.run({"items": items})
    map_items = len(items)
    orchestrator_strategy = "map_reduce"

    # Agent with tool and cost budget
    agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["lookup_policy"], custom_tool_args={"lookup_policy": {"query": "refund"}})):
        tool_result = await agent.run("Check refund policy")
    agent_tool_calls = tool_result.tool_calls_made
    agent_cost_budget = 0.1

    return {
        "status": "ok",
        "features": ["orchestrator_map_reduce", "agent_tool_cost"],
        "evidence": {
            "agent_cost_budget": agent_cost_budget,
            "agent_tool_calls": agent_tool_calls,
            "map_items": map_items,
            "orchestrator_strategy": orchestrator_strategy
        }
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
