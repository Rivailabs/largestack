import pytest
import sys
sys.path.insert(0, '.')
from jarvis_core import JarvisCore

@pytest.fixture
def core():
    return JarvisCore()

def test_remember_recall(core):
    core.remember('name', 'Alice')
    assert core.recall('name') == 'Alice'
    core.remember('data', {'a': 1, 'b': [2, 3]})
    assert core.recall('data') == {'a': 1, 'b': [2, 3]}
    assert core.recall('nonexistent') is None

def test_plan_day(core):
    tasks = ['code', 'meeting', 'review']
    result = core.plan_day(tasks)
    assert len(result) == 3
    assert result[0] == {'task': 'code'}
    assert result[1] == {'task': 'meeting'}
    assert result[2] == {'task': 'review'}

def test_decide_action_risky(core):
    risky_actions = ['send_email', 'move_file', 'delete_file', 'publish_social', 'refund_payment', 'write_production']
    for action in risky_actions:
        result = core.decide_action(action, {})
        assert result == {'decision': 'require_approval', 'executed': False}

def test_decide_action_safe(core):
    result = core.decide_action('read_file', {'path': '/tmp/test.txt'})
    assert result == {'decision': 'approved', 'executed': True}
