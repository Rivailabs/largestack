import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'team_parallel' in result['features']
    assert 'memory_isolation' in result['features']
    evidence = result['evidence']
    assert 'cross_user_leak' in evidence
    assert evidence['cross_user_leak'] == False
    assert 'memory_messages' in evidence
    assert evidence['memory_messages'] >= 2
    assert 'team_output' in evidence
    assert evidence['team_output'] != ''
    assert 'team_strategy' in evidence
    assert evidence['team_strategy'] == 'parallel'
