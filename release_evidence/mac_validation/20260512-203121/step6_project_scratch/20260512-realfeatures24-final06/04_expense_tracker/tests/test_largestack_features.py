import pytest
import asyncio
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "rag_citations" in result["features"]
    assert "guardrails_pii" in result["features"]
    evidence = result["evidence"]
    assert "rag_context" in evidence
    assert "rag_tool_calls" in evidence
    assert "redacted_text" in evidence
    assert "[Source" in evidence["rag_context"]
    assert "test@example.com" not in evidence["redacted_text"]
