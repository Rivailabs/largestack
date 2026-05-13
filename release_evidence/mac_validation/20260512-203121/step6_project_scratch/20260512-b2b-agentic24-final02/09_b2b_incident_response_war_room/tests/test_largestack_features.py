import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'workflow_dag' in result['features']
    assert 'rag_citations' in result['features']
    evidence = result['evidence']
    assert 'workflow_status' in evidence
    assert 'workflow_steps' in evidence
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert '[Source' in evidence['rag_context']
