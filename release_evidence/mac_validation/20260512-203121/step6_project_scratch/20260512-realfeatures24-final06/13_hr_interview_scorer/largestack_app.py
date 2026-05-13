import asyncio
from types import SimpleNamespace

from largestack import Agent, tool, create_guardrails
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up company policy based on query."""
    # Simulated policy lookup
    policies = {
        'refund': 'Refund policy: Full refund within 30 days.',
        'return': 'Return policy: Items must be returned within 14 days.',
        'shipping': 'Shipping policy: Free shipping on orders over $50.'
    }
    return policies.get(query.lower(), 'Policy not found.')

async def run_largestack_smoke() -> dict:
    """Execute selected LARGESTACK features and return results."""
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
        result = await agent.run("What is the refund policy?")
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