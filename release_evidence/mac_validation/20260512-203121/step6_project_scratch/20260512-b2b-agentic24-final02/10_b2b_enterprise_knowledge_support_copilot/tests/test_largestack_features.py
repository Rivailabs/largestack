import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'guardrails_pii' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert 'redacted_text' in evidence
    assert 'test@example.com' not in evidence['redacted_text']
    assert 'trace_id' in evidence
    assert 'total_cost' in evidence
    assert evidence['total_cost'] >= 0
    assert 'captured_messages' in evidence
    assert evidence['captured_messages'] >= 2
    assert 'redacted_log' in evidence
    assert 'sk-' not in evidence['redacted_log']
