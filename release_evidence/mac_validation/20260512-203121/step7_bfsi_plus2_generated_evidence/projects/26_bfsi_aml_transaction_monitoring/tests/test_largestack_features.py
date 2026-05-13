import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'orchestrator_router' in result['features']
    assert 'rag_citations' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert evidence['orchestrator_strategy'] == 'router'
    assert 'route_output' in evidence
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert 'trace_id' in evidence
    assert 'captured_messages' in evidence
    assert 'total_cost' in evidence
    assert 'redacted_log' in evidence
    assert '[REDACTED]' in evidence['redacted_log']
