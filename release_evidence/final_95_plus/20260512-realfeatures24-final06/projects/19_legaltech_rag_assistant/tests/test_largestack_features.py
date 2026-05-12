import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "team_parallel" in result["features"]
    assert "memory_isolation" in result["features"]
    evidence = result["evidence"]
    assert "team_output" in evidence
    assert evidence["team_strategy"] == "parallel"
    assert evidence["team_output"] != ""
    assert evidence["memory_messages"] >= 2
    assert evidence["cross_user_leak"] == False
