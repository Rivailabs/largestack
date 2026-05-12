# Orchestration Guide

LARGESTACK exposes three levels of orchestration. Use the simplest one that fits your automation.

## 1. Team

Use `Team` when you want a simple multi-agent chain or parallel fan-out.

```python
from largestack import Agent, Team

researcher = Agent(name="researcher", llm="deepseek/deepseek-chat")
writer = Agent(name="writer", llm="deepseek/deepseek-chat")

team = Team(agents=[researcher, writer], strategy="sequential")
result = await team.run("Research and summarize AI agents")
```

Best for:

- quick demos
- linear collaboration
- one input, several agent opinions

## 2. Workflow

Use `Workflow` when dependency order matters.

```python
from largestack import Agent, Workflow

extractor = Agent(name="extract", llm="deepseek/deepseek-chat")
validator = Agent(name="validate", llm="deepseek/deepseek-chat")
reporter = Agent(name="report", llm="deepseek/deepseek-chat")

wf = Workflow("rta-pipeline", mode="dag")
wf.add_node("extract", extractor)
wf.add_node("validate", validator, deps=["extract"])
wf.add_node("report", reporter, deps=["validate"])

result = await wf.run({"task": "Extract, validate, and report"})
```

Best for:

- production pipelines
- deterministic step ordering
- data extraction/validation/reporting flows

## 3. Orchestrator

Use `Orchestrator` when you want one public facade over common orchestration strategies.

```python
from largestack import Agent, Orchestrator

extractor = Agent(name="extractor", llm="deepseek/deepseek-chat")
validator = Agent(name="validator", llm="deepseek/deepseek-chat")
reporter = Agent(name="reporter", llm="deepseek/deepseek-chat")

orch = Orchestrator(
    name="rta-flow",
    strategy="dag",
    agents=[extractor, validator, reporter],
    flow=[("extractor", "validator"), ("validator", "reporter")],
    cost_budget=2.0,
)

result = await orch.run({"task": "Validate BOM and write report"})
print(result.output, result.trace_id, result.total_cost)
```

## Public `Orchestrator` strategies

| Strategy | Use when | Required setup |
|---|---|---|
| `sequential` | Agents should run one after another. | `agents=[a,b,c]` |
| `parallel` | Agents should run concurrently and combine output. | `agents=[a,b,c]` |
| `dag` | Steps have dependencies. | `agents=[...]`, `flow=[("a","b")]` |
| `state_machine` | State transitions drive execution. | `agents=[...]`, transition config via workflow-level API if needed |
| `router` | A classifier routes a request to a specialist. | `classifier=triage`, `routes={"billing": billing}` |
| `supervisor` | A manager agent repeatedly chooses specialists until done. | `supervisor_agent=manager`, `routes={"writer": writer}` |
| `map_reduce` | Many inputs should be processed and then synthesized. | `mapper=mapper_agent`, `reducer=reducer_agent` |

## Router example

```python
from largestack import Agent, Orchestrator

triage = Agent(name="triage", instructions="Choose billing or technical.")
billing = Agent(name="billing", instructions="Handle invoices and refunds.")
technical = Agent(name="technical", instructions="Handle bugs and implementation.")

orch = Orchestrator(
    strategy="router",
    classifier=triage,
    routes={"billing": billing, "technical": technical},
    default_route="technical",
)

result = await orch.run("I was charged twice last month")
```

## Supervisor example

```python
manager = Agent(name="manager", instructions="Choose the next specialist or FINAL_ANSWER.")
researcher = Agent(name="researcher", instructions="Gather facts.")
writer = Agent(name="writer", instructions="Write the final brief.")

orch = Orchestrator(
    strategy="supervisor",
    supervisor_agent=manager,
    routes={"researcher": researcher, "writer": writer},
    max_iterations=5,
)

result = await orch.run("Create a short market brief")
print(result.output)
print(result.steps)
```

## Map-reduce example

```python
mapper = Agent(name="summarizer", instructions="Summarize one document.")
reducer = Agent(name="synthesizer", instructions="Combine summaries into one report.")

orch = Orchestrator(
    strategy="map_reduce",
    mapper=mapper,
    reducer=reducer,
    max_concurrency=5,
)

result = await orch.run({"items": ["doc A text", "doc B text", "doc C text"]})
```

## Choosing the right pattern

| Problem | Recommended pattern |
|---|---|
| Simple research → write → review | `Team(strategy="sequential")` or `Orchestrator(strategy="sequential")` |
| Independent reviewers | `Team(strategy="parallel")` or `Orchestrator(strategy="parallel")` |
| Engineering automation | `Workflow(mode="dag")` or `Orchestrator(strategy="dag")` |
| Customer support triage | `Orchestrator(strategy="router")` |
| Complex open-ended planning | `Orchestrator(strategy="supervisor")` |
| 100 documents/invoices/log chunks | `Orchestrator(strategy="map_reduce")` |

## Production guidance

For production automation, always configure:

- cost budget
- max turns / max iterations
- guardrails
- tenant/RBAC policy
- trace/cost monitoring
- timeout and retry behavior
- human approval before irreversible actions

Advanced swarm, debate, saga, and custom graph primitives remain available under their dedicated modules while their public contracts stabilize.
