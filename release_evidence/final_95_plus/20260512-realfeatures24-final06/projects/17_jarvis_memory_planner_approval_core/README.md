# jarvis_memory_planner_approval_core

A core module for memory, planning, and action approval with a LARGESTACK integration demonstrating workflow DAG and tool policy approval features.

## Run

```bash
python -c "from jarvis_core import JarvisCore; j=JarvisCore(':memory:'); j.remember('prefs', {'focus':'maker'}); print(j.recall('prefs')['focus'])"
```

## Test

```bash
pip install pytest largestack
pytest tests/
```

## LARGESTACK smoke test

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
