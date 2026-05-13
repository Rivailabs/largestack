import uuid

_tasks = {}

def create_task(title, owner=None):
    if not title:
        raise ValueError("title cannot be empty")
    task_id = str(uuid.uuid4())
    task = {"id": task_id, "title": title, "owner": owner, "done": False}
    _tasks[task_id] = task
    return task

def list_tasks(owner=None):
    if owner is None:
        return list(_tasks.values())
    return [t for t in _tasks.values() if t.get("owner") == owner]

def complete_task(task_id):
    task = _tasks.get(task_id)
    if task is None:
        raise KeyError(f"Task {task_id} not found")
    task["done"] = True
    return task

def health():
    return {"status": "ok"}
