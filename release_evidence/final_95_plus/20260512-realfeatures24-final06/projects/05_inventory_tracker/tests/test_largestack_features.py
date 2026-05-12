import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "orchestrator_router" in result["features"]
    assert "team_parallel" in result["features"]
    assert result["evidence"]["orchestrator_strategy"] == "router"
    assert result["evidence"]["route_output"] == "routed ok"
    assert result["evidence"]["team_strategy"] == "parallel"
    team_output = result["evidence"]["team_output"]
    assert "a" in team_output
    assert "b" in team_output
