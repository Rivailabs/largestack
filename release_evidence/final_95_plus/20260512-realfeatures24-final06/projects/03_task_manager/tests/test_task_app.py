import pytest
from task_app import create_task, list_tasks, complete_task, health

def setup_function():
    # Clear internal state by importing and reassigning
    import task_app
    task_app._tasks.clear()

def test_create_task():
    t = create_task('ship tests', owner='qa')
    assert t['title'] == 'ship tests'
    assert t['owner'] == 'qa'
    assert t['done'] is False

def test_create_task_empty_title():
    with pytest.raises(ValueError):
        create_task('')

def test_list_tasks():
    create_task('task1', owner='qa')
    create_task('task2', owner='dev')
    qa_tasks = list_tasks('qa')
    assert len(qa_tasks) == 1
    assert qa_tasks[0]['title'] == 'task1'

def test_complete_task():
    t = create_task('test', owner='qa')
    result = complete_task(t['id'])
    assert result['done'] is True

def test_health():
    assert health() == {'status': 'ok'}
