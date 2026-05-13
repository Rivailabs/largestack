import pytest
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "orchestrator_router" in result["features"]
    assert "memory_isolation" in result["features"]
    evidence = result["evidence"]
    assert evidence["orchestrator_strategy"] == "router"
    assert evidence["route_output"] == "routed ok"
    assert evidence["memory_messages"] >= 2
    assert evidence["cross_user_leak"] is False
