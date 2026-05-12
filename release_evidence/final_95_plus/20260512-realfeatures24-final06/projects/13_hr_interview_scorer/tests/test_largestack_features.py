import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'agent_tool_cost' in result['features']
    assert 'guardrails_pii' in result['features']
    assert 'agent_tool_calls' in result['evidence']
    assert 'agent_cost_budget' in result['evidence']
    assert 'redacted_text' in result['evidence']
    # Verify redacted text does not contain raw email
    assert 'test@example.com' not in result['evidence']['redacted_text']
    # Verify agent_tool_calls is a list (may be empty if no calls made, but tool is registered)
    assert isinstance(result['evidence']['agent_tool_calls'], list)
    # Verify cost_budget is set
    assert result['evidence']['agent_cost_budget'] == 0.1