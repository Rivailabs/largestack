import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result["status"] == "ok"
    assert "rag_citations" in result["features"]
    assert "observability_trace" in result["features"]
    evidence = result["evidence"]
    assert "rag_context" in evidence
    assert "rag_tool_calls" in evidence
    assert "trace_id" in evidence
    assert "total_cost" in evidence
    assert "captured_messages" in evidence
    assert "redacted_log" in evidence
    assert evidence["captured_messages"] >= 2
    assert evidence["total_cost"] >= 0
    assert "[REDACTED]" in evidence["redacted_log"]
    assert "sk-" not in evidence["redacted_log"]
