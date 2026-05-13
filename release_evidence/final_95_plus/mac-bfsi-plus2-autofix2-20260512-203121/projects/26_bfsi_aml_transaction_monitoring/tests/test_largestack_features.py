import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'orchestrator_router' in result['features']
    assert 'rag_citations' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert evidence['orchestrator_strategy'] == 'router'
    assert evidence['route_output'] is not None
    assert '[Source' in evidence['rag_context']
    assert len(evidence['rag_tool_calls']) > 0
    assert evidence['trace_id'] is not None
    assert evidence['captured_messages'] >= 2
    assert evidence['total_cost'] >= 0
    assert 'REDACTED' in evidence['redacted_log']
