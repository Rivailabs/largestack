import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'memory_isolation' in result['features']
    ev = result['evidence']
    assert '[Source' in ev['rag_context']
    assert len(ev['rag_tool_calls']) > 0
    assert ev['memory_messages'] >= 2
    assert ev['cross_user_leak'] == False
