import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "orchestrator_map_reduce" in result["features"]
    assert "agent_tool_cost" in result["features"]
    evidence = result["evidence"]
    assert evidence["agent_cost_budget"] == 0.1
    assert isinstance(evidence["agent_tool_calls"], list)
    assert evidence["map_items"] >= 3
    assert evidence["orchestrator_strategy"] == "map_reduce"
