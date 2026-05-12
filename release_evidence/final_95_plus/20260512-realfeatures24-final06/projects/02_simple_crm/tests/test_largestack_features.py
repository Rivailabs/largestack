import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from largestack_app import run_largestack_smoke
import asyncio

@pytest.mark.asyncio
async def test_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "team_sequential" in result["features"]
    assert "memory_isolation" in result["features"]
    evidence = result["evidence"]
    assert evidence["team_strategy"] == "sequential"
    assert evidence["team_output"] != ""
    assert evidence["memory_messages"] >= 2
    assert evidence["cross_user_leak"] == False
