# Agent API

## Basic Agent

```python
from largestack import Agent

agent = Agent(
    name="my-bot",
    llm="openai/gpt-4o-mini",
    instructions="Be helpful",
    cost_budget=0.50,
    max_turns=5,
)

result = await agent.run("Hello")
print(result.content, result.total_cost, result.trace_id)
```

## Typed Agent (Decorator API)

```python
from dataclasses import dataclass
from largestack.decorators import Agent, RunContext

@dataclass
class Deps:
    user_id: str

agent = Agent[Deps, str](
    "openai/gpt-4o-mini",
    deps_type=Deps,
    instructions="Be helpful",
)

@agent.tool
async def search(ctx: RunContext[Deps], q: str) -> str:
    """Search."""
    return f"results: {q} for {ctx.deps.user_id}"

result = await agent.run("Find docs", deps=Deps(user_id="u1"))
```
