# agent_workflow_dashboard

A concise Python project that implements a workflow dashboard with run tracking, metrics, and Mermaid graph generation, plus a largestack_app.py that demonstrates guardrails PII redaction and observability tracing using the largestack library with TestModel overrides to avoid network calls.

## Requirements

- Python 3.8+
- largestack library (install with `pip install largestack`)

## Run

```bash
python workflow_dashboard.py
python largestack_app.py
```

## Test

```bash
pip install pytest
pytest tests/
```

## Usage

```python
from workflow_dashboard import record_run, metrics, mermaid_graph

record_run('agent-a', 'completed', cost=0.1, tokens=20, trace_id='t1')
print(metrics())
print(mermaid_graph(['agent-a', 'agent-b']))
```
