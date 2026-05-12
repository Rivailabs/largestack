import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'guardrails_pii' in result['features']
    assert 'typed_tools' in result['evidence']
    assert 'typed_output' in result['evidence']
    assert 'redacted_text' in result['evidence']
    assert 'test@example.com' not in result['evidence']['redacted_text']
