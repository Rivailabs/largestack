import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'team_parallel' in result['features']
    assert 'tool_policy_approval' in result['features']
    evidence = result['evidence']
    assert 'denied_tools' in evidence
    assert 'risky_action_executed' in evidence
    assert 'team_output' in evidence
    assert 'team_strategy' in evidence
    assert evidence['team_strategy'] == 'parallel'
    assert evidence['team_output'] != ''
    assert evidence['risky_action_executed'] == False
    assert 'dangerous_delete' in evidence['denied_tools']
