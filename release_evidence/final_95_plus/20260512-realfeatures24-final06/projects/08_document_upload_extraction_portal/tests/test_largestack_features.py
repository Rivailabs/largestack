import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'memory_isolation' in result['features']
    evidence = result['evidence']
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert 'memory_messages' in evidence
    assert 'cross_user_leak' in evidence
    assert evidence['memory_messages'] >= 2
    assert evidence['cross_user_leak'] == False
    assert '[Source' in evidence['rag_context']
