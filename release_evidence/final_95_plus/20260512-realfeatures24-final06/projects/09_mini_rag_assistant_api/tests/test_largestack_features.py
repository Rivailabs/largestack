import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'workflow_dag' in result['features']
    assert 'rag_citations' in result['features']
    assert 'workflow_status' in result['evidence']
    assert 'workflow_steps' in result['evidence']
    assert 'rag_context' in result['evidence']
    assert 'rag_tool_calls' in result['evidence']
