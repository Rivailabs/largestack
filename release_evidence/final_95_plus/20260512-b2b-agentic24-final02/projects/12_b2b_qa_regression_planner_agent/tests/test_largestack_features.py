import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import asyncio
from largestack_app import run_largestack_smoke

def test_run_largestack_smoke():
    result = asyncio.run(run_largestack_smoke())
    assert result['status'] == 'ok'
    assert 'typed_decorator_api' in result['features']
    assert 'workflow_dag' in result['features']
    assert result['evidence']['typed_output'] == 'typed ok'
    assert 'context_tool' in result['evidence']['typed_tools']
    assert 'plain_tool' in result['evidence']['typed_tools']
    assert result['evidence']['workflow_status'] == 'completed'
    assert result['evidence']['workflow_steps'] == 2
