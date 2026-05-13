import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'rag_citations' in result['features']
    assert 'tool_policy_approval' in result['features']
    evidence = result['evidence']
    assert 'rag_context' in evidence
    assert 'rag_tool_calls' in evidence
    assert 'denied_tools' in evidence
    assert 'risky_action_executed' in evidence
    assert evidence['risky_action_executed'] is False
    assert 'dangerous_delete' in evidence['denied_tools']
    assert '[Source' in evidence['rag_context']
