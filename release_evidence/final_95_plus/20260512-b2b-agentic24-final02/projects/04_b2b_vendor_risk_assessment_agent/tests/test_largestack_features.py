import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'guardrails_pii' in result['features']
    assert 'rag_context' in result['evidence']
    assert 'rag_tool_calls' in result['evidence']
    assert 'redacted_text' in result['evidence']
    # Check redacted text does not contain raw email
    assert 'test@example.com' not in result['evidence']['redacted_text']
    # Check rag_context contains '[Source'
    assert '[Source' in result['evidence']['rag_context']
