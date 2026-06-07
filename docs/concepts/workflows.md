# Workflows & Orchestration

LARGESTACK has three levels of multi-agent coordination, from simplest to most flexible:

| Level | Class | Shape | Import |
|-------|-------|-------|--------|
| Team | `Team` | run agents sequentially or in parallel | `from largestack import Team` |
| Workflow | `Workflow` | DAG (auto-parallelized) or state machine | `from largestack import Workflow` |
| Orchestrator | `Orchestrator` | one facade over 7 stable strategies | `from largestack import Orchestrator` |

All examples below run **offline** using `TestModel` from `largestack.testing` — no API keys, no network. Wrap agent construction with `guardrails=False` and swap in a `TestModel` via `agent.override(model=...)`.

## Team — sequential / parallel

`Team` coordinates a list of agents with structured context passing, per-agent error recovery, and a cost budget.

```python
from largestack import Team

team = Team(
    agents=[researcher, writer, reviewer],
    strategy="sequential",      # or "parallel"
    cost_budget=2.00,           # stop when accumulated cost hits this (0 = no cap)
    on_error="skip",            # "fail" | "skip" | "retry"
    retries_per_agent=2,
)
result = await team.run("Write a market analysis")
```

- **sequential** — each agent's output is threaded into the next agent's prompt via `AgentContext`. Returns the last agent's `AgentResult`.
- **parallel** — all agents run concurrently on the same task; outputs are concatenated into one `AgentResult`.

`on_error="skip"` drops a failing agent and continues; `"fail"` re-raises; combine with `fallback_map={name: fallback_agent}` for per-agent fallbacks.

## Workflow — DAG or state machine

`Workflow` accepts `Agent` objects (or async/sync `(state: dict) -> dict` handlers) as nodes. A `dag` workflow auto-parallelizes independent nodes and infers start/end from the dependency graph; a `state_machine` walks conditional edges.

```python
from largestack import Workflow

wf = Workflow("pipeline", mode="dag")     # mode: "dag" (default) or "state_machine"
wf.add_agent(research)                    # node name = agent.name
wf.add_agent(write, deps=["research"])    # runs after "research"
result = await wf.run({"task": "Analyze AI trends"})

result.final_output     # output of the last node
result.steps            # [{name, output, cost}, ...]
result.total_cost
result.status           # "completed" | "error"
```

`add_node(name, handler, deps=[...])` is the lower-level form; `add_agent(agent, deps=...)` is sugar for `add_node(agent.name, agent, deps)`. For `state_machine` mode use `add_edge(src, tgt, condition=fn)`, `set_start(name)`, and `set_end(*names)` — these raise on a DAG (which has no explicit start/end). The DAG validates the graph before running and raises a clear `ValueError` on missing deps or cycles.

## Orchestrator — the public facade

`Orchestrator` is one stable entry point over the most common production shapes. It normalizes every run to an `OrchestratorResult` (`output`, `strategy`, `steps`, `total_cost`, `metadata`, `trace_id`, `raw`).

```python
from largestack import Orchestrator

orch = Orchestrator(
    strategy="dag",
    agents={"extractor": extractor, "validator": validator},
    flow=[("extractor", "validator")],
)
result = await orch.run({"task": "extract and validate"})
# result.run_sync(task) is the synchronous wrapper for scripts/notebooks
```

`Orchestrator.supported_strategies()` lists the seven stable strategies. Inputs vary by strategy:

| Strategy | Required args | Backed by |
|----------|---------------|-----------|
| `sequential` | `agents=[...]` | `Team` |
| `parallel` | `agents=[...]` | `Team` |
| `dag` | `agents={name: agent}`, `flow=[(src, dst)]` | `Workflow` |
| `state_machine` | `agents={name: agent}`, `flow=[...]` | `Workflow` |
| `router` | `classifier=`, `routes={name: agent}`, `default_route=` | `Router` |
| `supervisor` | `supervisor_agent=`, specialist `agents`/`routes` | `Supervisor` |
| `map_reduce` | `mapper=`, `reducer=` (task carries `items`) | `MapReduce` |

`durable=True` writes run-level checkpoints (started/completed/failed) via a checkpoint store so a run is resumable/auditable; pass `thread_id=` / `checkpoint_db_path=` / `resume_completed=True` to control it. This is run-level, not LangGraph-style per-node replay.

## All 11 orchestration patterns

The facade exposes 7 stable strategies. Four more advanced primitives ship under `largestack._orchestrate` (and `largestack._core.multiagent`) — usable directly while their public API shapes settle.

| # | Pattern | How to reach it | Status |
|---|---------|-----------------|--------|
| 1 | Sequential | `Orchestrator(strategy="sequential")` / `Team(strategy="sequential")` | stable public |
| 2 | Parallel | `Orchestrator(strategy="parallel")` / `Team(strategy="parallel")` | stable public |
| 3 | DAG | `Orchestrator(strategy="dag")` / `Workflow(mode="dag")` | stable public |
| 4 | State machine | `Orchestrator(strategy="state_machine")` / `Workflow(mode="state_machine")` | stable public |
| 5 | Router | `Orchestrator(strategy="router")` | stable public |
| 6 | Supervisor | `Orchestrator(strategy="supervisor")` | stable public |
| 7 | Map-reduce | `Orchestrator(strategy="map_reduce")` | stable public |
| 8 | Swarm (handoff) | `from largestack._core.multiagent import Swarm` | advanced — direct import, API evolving |
| 9 | Debate | `from largestack._orchestrate.debate import Debate` | advanced — direct import, API evolving |
| 10 | Erlang-style supervisor (restart) | `from largestack._orchestrate.supervisor import Supervisor` | advanced — direct import, API evolving |
| 11 | Structured-chat (JSON tool loop) | `from largestack._core.multiagent import StructuredChatAgent` | advanced — direct import, API evolving |

> The `_orchestrate` and `_core` packages also ship `SequentialPipeline`, `ParallelFanOut`, `Flow`, and a routing `Router` under their own names. Prefer the `Orchestrator` facade unless you need a primitive it doesn't cover.

## When to use which

| You want… | Use |
|-----------|-----|
| A fixed A→B→C pipeline | `sequential` |
| Same task, many agents at once, then merge | `parallel` |
| Fan-out/fan-in with explicit dependencies | `dag` |
| Loops / conditional transitions / retries-to-self | `state_machine` |
| Classify a request, then dispatch to one specialist | `router` |
| A central agent that decides who works next, iteratively | `supervisor` |
| Process N documents in parallel, then synthesize one answer | `map_reduce` |
| Agents that decide for themselves to hand off to a peer | `Swarm` (advanced) |
| Multiple agents critiquing/converging on one answer | `Debate` (advanced) |

## Example — sequential Orchestrator (offline)

```python
import asyncio
from largestack import Agent, Orchestrator
from largestack.testing import TestModel

async def main():
    researcher = Agent(name="researcher", instructions="research", guardrails=False)
    writer = Agent(name="writer", instructions="write", guardrails=False)

    with researcher.override(model=TestModel(custom_output_text="found facts")), \
         writer.override(model=TestModel(custom_output_text="final report")):
        orch = Orchestrator(strategy="sequential", agents=[researcher, writer])
        result = await orch.run("Write a brief")
        print(result.output)     # -> final report
        print(result.strategy)   # -> sequential

asyncio.run(main())
```

## Example — DAG Orchestrator (offline)

```python
import asyncio
from largestack import Agent, Orchestrator
from largestack.testing import TestModel

async def main():
    extractor = Agent(name="extractor", instructions="extract", guardrails=False)
    validator = Agent(name="validator", instructions="validate", guardrails=False)

    with extractor.override(model=TestModel(custom_output_text="extracted")), \
         validator.override(model=TestModel(custom_output_text="validated")):
        orch = Orchestrator(
            strategy="dag",
            agents={"extractor": extractor, "validator": validator},
            flow=[("extractor", "validator")],
        )
        result = await orch.run({"task": "extract and validate"})
        print(result.output)                          # -> validated
        print([s["name"] for s in result.steps])      # -> ['extractor', 'validator']

asyncio.run(main())
```

## Example — Workflow directly (offline)

```python
import asyncio
from largestack import Agent, Workflow
from largestack.testing import TestModel

async def main():
    research = Agent(name="research", guardrails=False)
    write = Agent(name="write", guardrails=False)

    with research.override(model=TestModel(custom_output_text="data")), \
         write.override(model=TestModel(custom_output_text="article")):
        wf = Workflow("pipeline", mode="dag")
        wf.add_agent(research)
        wf.add_agent(write, deps=["research"])
        result = await wf.run({"task": "Analyze AI trends"})
        print(result.final_output)   # -> article
        print(result.status)         # -> completed

asyncio.run(main())
```

## See also

- [Agents](agents.md)
- [Guardrails](guardrails.md)
- [Tools](tools.md)
