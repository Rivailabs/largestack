# Durable Orchestration

LARGESTACK now exposes run-level durable orchestration through `Orchestrator(durable=True)`.

```python
from largestack import Agent, Orchestrator

orch = Orchestrator(
    name="invoice-flow",
    strategy="sequential",
    agents=[extractor, validator, reporter],
    durable=True,
    thread_id="invoice-123",
)

result = await orch.run("process invoice")
```

Durable mode stores:

- `started` checkpoint
- `completed` checkpoint
- `failed` checkpoint on exception
- strategy, task, output, trace ID, cost, steps, metadata

## Resume completed runs

```python
orch = Orchestrator(
    name="invoice-flow",
    strategy="sequential",
    agents=[extractor, validator, reporter],
    durable=True,
    thread_id="invoice-123",
    resume_completed=True,
)
result = await orch.run("process invoice")
```

This returns the completed checkpoint without rerunning the flow.

## Honest limitation

This is **run-level durability**, not full LangGraph-style per-node checkpoint/replay/time-travel for every graph strategy. It is a production-useful audit/resume layer, and future work can add deterministic per-node replay.
