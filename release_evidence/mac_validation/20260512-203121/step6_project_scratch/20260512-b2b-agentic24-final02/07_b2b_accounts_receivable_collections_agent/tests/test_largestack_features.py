import sys
sys.path.insert(0, '.')
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'orchestrator_map_reduce' in result['features']
    assert 'agent_tool_cost' in result['features']
    assert result['evidence']['orchestrator_strategy'] == 'map_reduce'
    assert result['evidence']['map_items'] >= 3
    assert result['evidence']['agent_cost_budget'] == 0.1
    assert isinstance(result['evidence']['agent_tool_calls'], list)
