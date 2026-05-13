import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from largestack_app import run_largestack_smoke

def test_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert 'typed_tools' in evidence
    assert 'typed_output' in evidence
    assert evidence['typed_output'] == 'typed ok'
    assert 'trace_id' in evidence
    assert evidence['captured_messages'] >= 2
    assert evidence['total_cost'] >= 0
    assert 'REDACTED' in evidence['redacted_log']
