import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "typed_decorator_api" in result["features"]
    assert "memory_isolation" in result["features"]
    evidence = result["evidence"]
    assert evidence["cross_user_leak"] == False
    assert evidence["memory_messages"] >= 2
    assert evidence["typed_output"] == "typed ok"
    assert "context_tool" in evidence["typed_tools"]
    assert "plain_tool" in evidence["typed_tools"]
