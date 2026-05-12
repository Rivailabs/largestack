import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert 'captured_messages' in evidence
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert 'redacted_log' in evidence
    assert 'total_cost' in evidence
    assert 'trace_id' in evidence
    # rag_context should contain '[Source'
    assert '[Source' in evidence['rag_context']
    # captured_messages >= 2
    assert evidence['captured_messages'] >= 2
    # total_cost >= 0
    assert evidence['total_cost'] >= 0
    # redacted_log should not contain raw sk-
    assert 'sk-' not in evidence['redacted_log']
