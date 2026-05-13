import pytest
import asyncio
from largestack_app import run_largestack_smoke

def test_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'orchestrator_router' in result['features']
    assert 'agent_tool_cost' in result['features']
    assert 'agent_cost_budget' in result['evidence']
    assert 'agent_tool_calls' in result['evidence']
    assert 'orchestrator_strategy' in result['evidence']
    assert 'route_output' in result['evidence']
