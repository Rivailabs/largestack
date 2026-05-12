import asyncio
from types import SimpleNamespace
from largestack import Agent, tool
from largestack.testing import TestModel
from largestack.guardrails import create_guardrails

@tool
def lookup_policy(query: str) -> str:
    """Look up cost policy for a given query."""
    # Simulated policy lookup
    return f"Policy for '{query}': Approval required for any action exceeding 20% over baseline."

async def run_largestack_smoke() -> dict:
    """
    Execute selected LARGESTACK features: agent_tool_cost and guardrails_pii.
    Returns dict with status, features list, and evidence.
    """
    features = []
    evidence = {}

    # Feature: agent_tool_cost
    agent = Agent(
        name="cost_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(
        call_tools=["lookup_policy"],
        custom_tool_args={"lookup_policy": {"query": "refund"}}
    )):
        result = await agent.run("Check policy for refund")
    features.append("agent_tool_cost")
    evidence["agent_tool_calls"] = result.tool_calls_made
    evidence["agent_cost_budget"] = agent.cost_budget

    # Feature: guardrails_pii
    guardrails = create_guardrails(pii=True, injection=True, pii_action="redact")
    response = SimpleNamespace(content="Email test@example.com")
    await guardrails.check_output(response)
    features.append("guardrails_pii")
    evidence["redacted_text"] = response.content

    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }

if __name__ == "__main__":
    result = asyncio.run(run_largestack_smoke())
    print(result)
