# Task Manager

A simple task manager project with:
- `task_app.py`: core task CRUD functions (create_task, list_tasks, complete_task, health)
- `largestack_app.py`: async smoke test using LARGESTACK workflow_dag and observability_trace features

## Run Tests

```bash
pip install pytest pytest-asyncio largestack
pytest tests/
```

## Usage

```python
from task_app import create_task, list_tasks, complete_task, health

t = create_task('ship tests', owner='qa')
assert list_tasks('qa')
assert complete_task(t['id'])['done'] is True
assert health() == {'status': 'ok'}
```

## LARGESTACK Smoke Test

Run the async smoke test:

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
