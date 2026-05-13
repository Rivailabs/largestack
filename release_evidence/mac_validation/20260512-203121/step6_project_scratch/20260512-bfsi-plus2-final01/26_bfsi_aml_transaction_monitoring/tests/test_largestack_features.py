import pytest

from largestack.testing import block_model_requests
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_largestack_smoke_executes_real_features():
    with block_model_requests():
        out = await run_largestack_smoke()
    assert out["status"] == "ok"
    assert set(out["features"]) == {
        "orchestrator_router",
        "rag_citations",
        "observability_trace",
    }
    evidence = out["evidence"]
    assert evidence["orchestrator_strategy"] == "router"
    assert evidence["route_output"]
    context = (
        "\n".join(evidence["rag_context"])
        if isinstance(evidence["rag_context"], list)
        else str(evidence["rag_context"])
    )
    assert "[Source" in context
    assert evidence["rag_tool_calls"]
    assert evidence["trace_id"]
    assert evidence["captured_messages"] >= 2
    assert evidence["total_cost"] >= 0
    assert "sk-" not in evidence["redacted_log"]
