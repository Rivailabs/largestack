# Multi-Agent Workflow

LARGESTACK template for hierarchical multi-agent systems.

Three specialists: researcher → writer → critic.

## Run
```bash
pip install largestack
export LARGESTACK_OPENAI_API_KEY="sk-..."
largestack run workflow.yaml --task "Write a brief on agentic AI"
```

## Pattern: Supervisor / Swarm

This template uses a **graph-based** workflow. LARGESTACK also ships:
- `Supervisor` — central orchestrator routes to specialists
- `Swarm` — agents hand off to each other peer-to-peer

See `largestack._core.multiagent` for examples.
