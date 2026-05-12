import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "typed_decorator_api" in result["features"]
    assert "guardrails_pii" in result["features"]
    evidence = result["evidence"]
    assert "redacted_text" in evidence
    assert "typed_output" in evidence
    assert "typed_tools" in evidence
    assert "test@example.com" not in evidence["redacted_text"]
    assert evidence["typed_output"] == "typed ok"
    assert isinstance(evidence["typed_tools"], list)
