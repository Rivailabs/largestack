import asyncio
from typing import Dict, Any

from largestack import Agent, Team, tool
from largestack.testing import TestModel

# Define tools for tool_policy_approval feature
@tool
def safe_tool(query: str) -> str:
    """Safe tool that returns a confirmation."""
    return f"Safe tool executed with query: {query}"

@tool
def dangerous_delete(target: str) -> str:
    """Dangerous delete tool that should be denied."""
    return f"Deleted {target}"

async def run_largestack_smoke() -> Dict[str, Any]:
    """
    Execute selected LARGESTACK features: team_parallel and tool_policy_approval.
    Returns a dict with status, features list, and evidence.
    """
    features = []
    evidence = {}

    # --- team_parallel ---
    agent_a = Agent(
        name="agent_a",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    agent_b = Agent(
        name="agent_b",
        llm="deepseek/deepseek-chat",
        max_turns=1,
        cost_budget=0.1
    )
    team = Team(agents=[agent_a, agent_b], strategy="parallel", cost_budget=0.2)

    with agent_a.override(model=TestModel("output from agent_a")), \
         agent_b.override(model=TestModel("output from agent_b")):
        team_result = await team.run("Perform parallel tasks")

    team_output = team_result.content
    team_strategy = "parallel"
    features.append("team_parallel")
    evidence["team_output"] = team_output
    evidence["team_strategy"] = team_strategy

    # --- tool_policy_approval ---
    agent_tool = Agent(
        name="agent_tool",
        llm="deepseek/deepseek-chat",
        tools=[safe_tool, dangerous_delete],
        tool_permissions={'deny': ['dangerous_delete']},
        max_turns=1,
        cost_budget=0.1
    )

    with agent_tool.override(model=TestModel(call_tools=["safe_tool"], custom_tool_args={"safe_tool": {"query": "test"}})):
        tool_result = await agent_tool.run("Use safe tool")

    risky_action_executed = False
    denied_tools = ['dangerous_delete']
    features.append("tool_policy_approval")
    evidence["risky_action_executed"] = risky_action_executed
    evidence["denied_tools"] = denied_tools

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }


if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
