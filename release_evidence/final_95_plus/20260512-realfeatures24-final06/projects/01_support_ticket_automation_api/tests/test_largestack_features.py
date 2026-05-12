import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'agent_tool_cost' in result['features']
    assert 'tool_policy_approval' in result['features']
    evidence = result['evidence']
    assert 'agent_cost_budget' in evidence
    assert 'agent_tool_calls' in evidence
    assert 'denied_tools' in evidence
    assert 'risky_action_executed' in evidence
    assert evidence['denied_tools'] == ['dangerous_delete']
    assert evidence['risky_action_executed'] is False
