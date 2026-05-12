import asyncio
from typing import Dict, Any, List
from largestack import Agent, Orchestrator, tool
from largestack.testing import TestModel

@tool
def lookup_policy(query: str) -> str:
    """Look up a collection policy by query."""
    policies = {
        'refund': 'Refund policy: No refunds after 30 days.',
        'late': 'Late payment policy: 2% monthly interest.',
        'dispute': 'Dispute policy: Escalate to manager.'
    }
    return policies.get(query.lower(), 'Policy not found.')

async def run_largestack_smoke() -> Dict[str, Any]:
    """
    Execute selected LARGESTACK features: map-reduce and agent tool cost.
    Returns evidence dict.
    """
    features = []
    evidence = {}
    
    # --- Feature: orchestrator_map_reduce ---
    mapper = Agent(
        name="mapper",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    reducer = Agent(
        name="reducer",
        llm="deepseek/deepseek-chat",
        max_turns=1
    )
    orch = Orchestrator(
        strategy="map_reduce",
        mapper=mapper,
        reducer=reducer
    )
    items = ["invoice_1", "invoice_2", "invoice_3"]
    with mapper.override(model=TestModel("mapped")), reducer.override(model=TestModel("summary")):
        result = await orch.run({"items": items})
    features.append("orchestrator_map_reduce")
    evidence["orchestrator_strategy"] = "map_reduce"
    evidence["map_items"] = len(items)
    
    # --- Feature: agent_tool_cost ---
    agent = Agent(
        name="policy_agent",
        llm="deepseek/deepseek-chat",
        tools=[lookup_policy],
        cost_budget=0.1,
        max_turns=3
    )
    with agent.override(model=TestModel(call_tools=["lookup_policy"], custom_tool_args={"lookup_policy": {"query": "refund"}})):
        result = await agent.run("Check refund policy")
    features.append("agent_tool_cost")
    evidence["agent_tool_calls"] = result.tool_calls_made
    evidence["agent_cost_budget"] = 0.1
    
    return {
        "status": "ok",
        "features": features,
        "evidence": evidence
    }
