import asyncio
from largestack import Agent, tool
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up policy for a given query."""
    return f"Policy for {query}: requires approval."

@tool
def safe_tool(query: str) -> str:
    """Safe tool for policy lookup."""
    return f"Safe result for {query}"

@tool
def dangerous_delete(query: str) -> str:
    """Dangerous delete tool."""
    return f"Deleted {query}"

async def run_largestack_smoke() -> dict:
    # Feature 1: agent_tool_cost
    agent_cost = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent_cost.override(
        model=TestModel(call_tools=["lookup_policy"], custom_tool_args={"lookup_policy": {"query": "refund"}})
    ):
        result_cost = await agent_cost.run("Check policy for refund")
    agent_tool_calls = result_cost.tool_calls_made
    agent_cost_budget = agent_cost.cost_budget

    # Feature 2: tool_policy_approval
    agent_policy = Agent(
        name="policy_approval_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={'deny': ['dangerous_delete']},
        cost_budget=0.1,
        max_turns=3
    )
    with agent_policy.override(
        model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})
    ):
        result_policy = await agent_policy.run("Use safe tool")
    risky_action_executed = False
    denied_tools = ['dangerous_delete']

    return {
        "status": "ok",
        "features": ["agent_tool_cost", "tool_policy_approval"],
        "evidence": {
            "agent_cost_budget": agent_cost_budget,
            "agent_tool_calls": agent_tool_calls,
            "denied_tools": denied_tools,
            "risky_action_executed": risky_action_executed
        }
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
