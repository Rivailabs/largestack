import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'workflow_dag' in result['features']
    assert 'team_sequential' in result['features']
    evidence = result['evidence']
    assert 'team_output' in evidence
    assert 'team_strategy' in evidence
    assert evidence['team_strategy'] == 'sequential'
    assert 'workflow_status' in evidence
    assert 'workflow_steps' in evidence
    assert evidence['workflow_steps'] > 0
