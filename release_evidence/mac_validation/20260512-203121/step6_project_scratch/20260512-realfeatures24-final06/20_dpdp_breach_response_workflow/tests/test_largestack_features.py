import pytest
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "agent_tool_cost" in result["features"]
    assert "orchestrator_router" in result["features"]
    evidence = result["evidence"]
    assert "agent_tool_calls" in evidence
    assert "agent_cost_budget" in evidence
    assert evidence["agent_cost_budget"] == 0.1
    assert "orchestrator_strategy" in evidence
    assert evidence["orchestrator_strategy"] == "router"
    assert "route_output" in evidence
    assert evidence["route_output"] == "routed ok"
