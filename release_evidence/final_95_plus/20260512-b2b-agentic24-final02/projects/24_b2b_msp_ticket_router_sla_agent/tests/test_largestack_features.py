import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_run_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'orchestrator_map_reduce' in result['features']
    assert 'guardrails_pii' in result['features']
    assert result['evidence']['orchestrator_strategy'] == 'map_reduce'
    assert result['evidence']['map_items'] >= 3
    assert 'test@example.com' not in result['evidence']['redacted_text']
