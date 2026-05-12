import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    # typed_decorator_api evidence
    assert 'typed_tools' in evidence
    assert 'typed_output' in evidence
    assert evidence['typed_output'] == 'typed ok'
    # observability_trace evidence
    assert 'trace_id' in evidence
    assert 'captured_messages' in evidence
    assert evidence['captured_messages'] >= 2
    assert 'total_cost' in evidence
    assert evidence['total_cost'] >= 0
    assert 'redacted_log' in evidence
    assert '[REDACTED]' in evidence['redacted_log']
    assert 'sk-' not in evidence['redacted_log']
