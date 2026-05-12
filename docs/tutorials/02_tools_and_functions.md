# Tutorial 2: Tools and Function Calling

Give your agent capabilities beyond text generation.

## Step 1: Define tools with `@tool`

```python
from largestack import Agent, tool

@tool
async def web_search(query: str) -> str:
    """Search the web for information."""
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(f"https://api.duckduckgo.com/?q={query}&format=json")
        return r.json().get("AbstractText", "No results found.")

@tool(timeout=10)
async def calculator(expression: str) -> str:
    """Evaluate a math expression safely."""
    import math
    safe = {k: getattr(math, k) for k in dir(math) if not k.startswith('_')}
    return str(eval(expression, {"__builtins__": {}}, safe))
```

Type hints become JSON Schema automatically. Docstrings become tool descriptions.

## Step 2: Give tools to your agent

```python
agent = Agent(
    name="research-assistant",
    instructions="Search the web and do calculations when needed.",
    tools=[web_search, calculator],
    llm="openai/gpt-4o-mini",
)
```

## Step 3: Run a task requiring tools

```python
result = await agent.run("What is the population of Tokyo? Calculate what percentage of Japan's 125M that is.")
print(result.content)
print(f"Tools used: {result.tool_calls_made}")
```

## Tool options

```python
@tool(timeout=60)       # 60s timeout (default: 30s)
@tool(retries=3)        # Retry on failure
@tool(name="search")    # Override name
```

## Next: [Multi-agent teams →](03_multi_agent_teams.md)
