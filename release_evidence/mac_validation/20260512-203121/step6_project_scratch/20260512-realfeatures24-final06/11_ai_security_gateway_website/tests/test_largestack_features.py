import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "team_parallel" in result["features"]
    assert "tool_policy_approval" in result["features"]
    evidence = result["evidence"]
    assert "denied_tools" in evidence
    assert "risky_action_executed" in evidence
    assert "team_output" in evidence
    assert "team_strategy" in evidence
    assert evidence["team_strategy"] == "parallel"
    assert evidence["team_output"] != ""
    assert evidence["risky_action_executed"] == False
    assert evidence["denied_tools"] == ["dangerous_delete"]