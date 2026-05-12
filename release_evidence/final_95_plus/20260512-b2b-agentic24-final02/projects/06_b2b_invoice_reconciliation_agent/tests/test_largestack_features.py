import sys
sys.path.insert(0, '.')
import pytest
from largestack_app import run_largestack_smoke

@pytest.mark.asyncio
async def test_largestack_smoke():
    result = await run_largestack_smoke()
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'memory_isolation' in result['features']
    evidence = result['evidence']
    assert 'typed_tools' in evidence
    assert 'typed_output' in evidence
    assert evidence['typed_output'] == 'typed ok'
    assert evidence['memory_messages'] >= 2
    assert evidence['cross_user_leak'] is False
