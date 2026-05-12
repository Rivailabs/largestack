import pytest
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "orchestrator_map_reduce" in result["features"]
    assert "team_sequential" in result["features"]
    evidence = result["evidence"]
    assert evidence["orchestrator_strategy"] == "map_reduce"
    assert evidence["map_items"] >= 3
    assert evidence["team_strategy"] == "sequential"
    assert evidence["team_output"] is not None and evidence["team_output"] != ""
