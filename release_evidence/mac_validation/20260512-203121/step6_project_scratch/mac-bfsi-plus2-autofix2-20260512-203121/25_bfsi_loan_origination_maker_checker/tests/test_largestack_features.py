import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from largestack_app import run_largestack_smoke


@pytest.mark.asyncio
async def test_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'workflow_dag' in result['features']
    assert 'tool_policy_approval' in result['features']
    assert 'guardrails_pii' in result['features']
    evidence = result['evidence']
    assert 'workflow_status' in evidence
    assert 'workflow_steps' in evidence
    assert evidence['workflow_steps'] >= 2
    assert evidence['risky_action_executed'] == False
    assert evidence['denied_tools'] == ['dangerous_delete']
    assert 'redacted_text' in evidence
    assert 'test@example.com' not in evidence['redacted_text']