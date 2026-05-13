import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'team_sequential' in result['features']
    assert 'memory_isolation' in result['features']
    evidence = result['evidence']
    assert evidence['team_strategy'] == 'sequential'
    assert evidence['team_output'] != ''
    assert evidence['memory_messages'] >= 2
    assert evidence['cross_user_leak'] is False
