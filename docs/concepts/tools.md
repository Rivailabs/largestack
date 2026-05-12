# Tools

```python
from largestack.decorators import Agent, RunContext

agent = Agent("openai/gpt-4o-mini")

# With context
@agent.tool
async def search(ctx: RunContext, q: str) -> str:
    """Search docs."""
    return f"results: {q}"

# Without context
@agent.tool_plain
def add(x: int, y: int) -> int:
    """Add numbers."""
    return x + y
```

Tools are auto-registered with JSON schema from type hints.
