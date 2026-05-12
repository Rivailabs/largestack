import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'guardrails_pii' in result['features']
    assert 'observability_trace' in result['features']
    evidence = result['evidence']
    assert 'redacted_text' in evidence
    assert 'test@example.com' not in evidence['redacted_text']
    assert 'trace_id' in evidence
    assert evidence['total_cost'] >= 0
    assert evidence['captured_messages'] >= 2
    assert 'sk-' not in evidence['redacted_log']
