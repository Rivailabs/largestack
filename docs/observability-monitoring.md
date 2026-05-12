# Observability, Monitoring, Feedback, and Cost

LARGESTACK provides local/self-hosted observability rather than requiring a SaaS-only platform.

## Runtime flow

```text
Agent/Workflow/Orchestrator run
  -> trace_id generated
  -> model/tool/runtime metrics recorded
  -> SQLite trace DB written best-effort
  -> /health, /metrics, dashboard APIs expose status
  -> Monitor facade reads traces and records feedback
  -> optional OTEL / Langfuse / Phoenix adapters export externally
```

## Public API

```python
from largestack import Monitor

monitor = Monitor()
print(monitor.summary())
traces = monitor.list_traces(limit=20)
if traces:
    monitor.record_feedback(traces[0]["trace_id"], rating=5, label="good")
    print(monitor.evaluate_trace(traces[0]["trace_id"]))
```

## Positioning

LARGESTACK observability is strong for self-hosted/local operations:

- trace listing
- trace detail
- feedback capture
- lightweight quality evaluation
- metrics endpoint
- dashboard
- optional OTEL/Langfuse/Phoenix export

It is not a full LangSmith replacement yet because LangSmith provides a managed platform for projects, traces, datasets, evals, annotation queues, alerts, and automations.
