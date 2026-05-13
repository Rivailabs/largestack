import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'tool_policy_approval' in result['features']
    evidence = result['evidence']
    assert 'denied_tools' in evidence
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert 'risky_action_executed' in evidence
    assert evidence['denied_tools'] == ['dangerous_delete']
    assert evidence['risky_action_executed'] == False
