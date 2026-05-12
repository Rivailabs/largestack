import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'workflow_dag' in result['features']
    evidence = result['evidence']
    assert 'typed_output' in evidence
    assert 'typed_tools' in evidence
    assert 'workflow_status' in evidence
    assert 'workflow_steps' in evidence
    assert evidence['typed_output'] == 'typed ok'
    assert isinstance(evidence['typed_tools'], list)
    assert evidence['workflow_steps'] > 0
