import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from largestack_app import run_largestack_smoke


def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'orchestrator_map_reduce' in result['features']
    assert 'team_sequential' in result['features']
    evidence = result['evidence']
    assert evidence['map_items'] >= 3
    assert evidence['orchestrator_strategy'] == 'map_reduce'
    assert evidence['team_strategy'] == 'sequential'
    assert evidence['team_output'] != ''
