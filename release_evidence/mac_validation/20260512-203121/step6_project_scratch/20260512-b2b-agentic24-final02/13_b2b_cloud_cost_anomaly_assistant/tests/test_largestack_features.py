import pytest
import asyncio
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'agent_tool_cost' in result['features']
    assert 'guardrails_pii' in result['features']
    evidence = result['evidence']
    assert 'agent_tool_calls' in evidence
    assert 'agent_cost_budget' in evidence
    assert 'redacted_text' in evidence
    # Verify redacted_text does not contain raw email
    assert 'test@example.com' not in evidence['redacted_text']
    # Verify agent_tool_calls is a list (may be empty due to TestModel override)
    assert isinstance(evidence['agent_tool_calls'], list)
    # Verify cost_budget is set
    assert evidence['agent_cost_budget'] == 0.1
