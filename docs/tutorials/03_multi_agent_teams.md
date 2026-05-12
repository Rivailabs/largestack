# Tutorial 3: Multi-Agent Teams

Coordinate multiple agents for complex tasks.

## Sequential Pipeline (A → B → C)

```python
from largestack import Agent, Team

researcher = Agent(
    name="researcher",
    instructions="Find 3 key facts about the topic. Be factual and specific.",
    llm="openai/gpt-4o-mini",
)

writer = Agent(
    name="writer",
    instructions="Take research findings and write a clear, engaging summary.",
    llm="openai/gpt-4o-mini",
)

reviewer = Agent(
    name="reviewer",
    instructions="Review the summary for accuracy. Fix any issues.",
    llm="openai/gpt-4o-mini",
)

team = Team(
    agents=[researcher, writer, reviewer],
    strategy="sequential",
)

result = await team.run("The impact of AI on healthcare in 2026")
print(result.content)       # Reviewed summary
print(f"Total cost: ${result.total_cost:.4f}")
```

## Parallel Fan-Out

```python
team = Team(
    agents=[agent_a, agent_b, agent_c],
    strategy="parallel",  # All run simultaneously
)
```

## Workflow (DAG)

```python
from largestack import Workflow

wf = Workflow("analysis", mode="dag")
wf.add_node("fetch", fetch_agent)
wf.add_node("analyze", analyze_agent, deps=["fetch"])
wf.add_node("visualize", viz_agent, deps=["fetch"])
wf.add_node("report", report_agent, deps=["analyze", "visualize"])
result = await wf.run({})
```

## Next: [Guardrails and safety →](04_guardrails.md)
