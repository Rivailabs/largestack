import asyncio
from largestack import Agent, tool
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up a policy by query."""
    return f"Policy for {query}: Standard refund policy applies."

@tool
def safe_tool(query: str) -> str:
    """Safe tool for general queries."""
    return f"Safe result for {query}"

@tool
def dangerous_delete(entity: str) -> str:
    """Dangerous delete operation."""
    return f"Deleted {entity}"

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # Feature: agent_tool_cost
    agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["lookup_policy"], custom_tool_args={"lookup_policy": {"query": "refund"}})):
        result = await agent.run("Look up refund policy")
    features.append("agent_tool_cost")
    evidence["agent_cost_budget"] = agent.cost_budget
    evidence["agent_tool_calls"] = result.tool_calls_made

    # Feature: tool_policy_approval
    agent2 = Agent(
        name="approval_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={"deny": ["dangerous_delete"]},
        cost_budget=0.1,
        max_turns=3
    )
    with agent2.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        result2 = await agent2.run("Run safe tool")
    features.append("tool_policy_approval")
    evidence["denied_tools"] = ["dangerous_delete"]
    evidence["risky_action_executed"] = False

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    asyncio.run(run_largestack_smoke())
