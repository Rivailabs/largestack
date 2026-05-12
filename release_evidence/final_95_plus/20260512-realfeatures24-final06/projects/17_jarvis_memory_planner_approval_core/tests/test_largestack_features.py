import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'workflow_dag' in result['features']
    assert 'tool_policy_approval' in result['features']
    evidence = result['evidence']
    assert 'denied_tools' in evidence
    assert 'risky_action_executed' in evidence
    assert 'workflow_status' in evidence
    assert 'workflow_steps' in evidence
    assert evidence['denied_tools'] == ['dangerous_delete']
    assert evidence['risky_action_executed'] is False
    assert evidence['workflow_steps'] >= 2
