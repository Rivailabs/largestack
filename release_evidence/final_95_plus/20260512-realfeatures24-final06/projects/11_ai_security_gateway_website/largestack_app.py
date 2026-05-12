import asyncio
from largestack import Agent, Team, tool
from largestack.testing import TestModel

@tool
def safe_tool(query: str) -> str:
    """Safe tool for querying."""
    return f"Processed: {query}"

@tool
def dangerous_delete(path: str) -> str:
    """Dangerous delete tool."""
    return f"Deleted {path}"

async def run_largestack_smoke() -> dict:
    features = []
    evidence = {}

    # team_parallel
    agent_a = Agent(name="agent_a", llm="deepseek/deepseek-chat", max_turns=1)
    agent_b = Agent(name="agent_b", llm="deepseek/deepseek-chat", max_turns=1)
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)
    with agent_a.override(model=TestModel("output from agent_a")), agent_b.override(model=TestModel("output from agent_b")):
        team_result = await team.run("parallel task")
    team_output = team_result.content
    features.append("team_parallel")
    evidence["team_output"] = team_output
    evidence["team_strategy"] = "parallel"

    # tool_policy_approval
    policy_agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={'deny': ['dangerous_delete']},
        cost_budget=0.1,
        max_turns=1
    )
    with policy_agent.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        result = await policy_agent.run("run safe tool")
    calls = result.tool_calls_made  # list of tool name strings
    risky_action_executed = any(c == "dangerous_delete" for c in calls)
    denied_tools = ["dangerous_delete"]
    features.append("tool_policy_approval")
    evidence["risky_action_executed"] = risky_action_executed
    evidence["denied_tools"] = denied_tools

    return {"status": "ok", "features": features, "evidence": evidence}

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
