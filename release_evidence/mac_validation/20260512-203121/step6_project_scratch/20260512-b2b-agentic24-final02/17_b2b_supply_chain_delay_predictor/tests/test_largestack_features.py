import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    assert evidence['risky_action_executed'] is False
    assert 'dangerous_delete' in evidence['denied_tools']
