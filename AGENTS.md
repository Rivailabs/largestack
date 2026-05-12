# LARGESTACK Agentic AI — Project Guidelines for AI Coding Tools

This is the LARGESTACK agentic AI framework codebase. When generating code for projects using LARGESTACK, follow these patterns:

## Idiomatic Patterns

### Use the typed decorator API (preferred over older Agent API)

```python
from dataclasses import dataclass
from largestack.decorators import Agent, RunContext, ModelRetry

@dataclass
class Deps:
    db: object
    user_id: str

agent = Agent[Deps, str](
    "openai/gpt-4o-mini",
    deps_type=Deps,
    instructions="Be helpful.",
)

@agent.tool
async def search(ctx: RunContext[Deps], query: str) -> str:
    """Search KB. Docstring becomes tool description."""
    return await ctx.deps.db.search(query, ctx.deps.user_id)

@agent.output_validator
def check(ctx, output: str) -> str:
    if "bad" in output:
        raise ModelRetry("Avoid certain words")
    return output
```

### For tools without context, use @agent.tool_plain
```python
@agent.tool_plain
def add(x: int, y: int) -> int:
    """Add numbers."""
    return x + y
```

### Test with TestModel/FunctionModel (no API calls)
```python
from largestack.testing import TestModel, block_model_requests

with block_model_requests():
    test_model = TestModel(custom_output_text="canned")
    # Inject via override
```

## Conventions

- Tools always document with docstrings (auto-extracted as description)
- First parameter type-annotated as `RunContext[Deps]` if context needed
- Use `Pydantic BaseModel` for output_type when structured
- Always set `cost_budget` and `max_retries`
- Use `largestack dev` for hot-reload local development

## Anti-Patterns (avoid)

- Don't use `dict` for tool params; use typed annotations
- Don't return raw dicts from tools; use Pydantic models
- Don't disable guardrails in production
- Don't log prompt content (PII risk)
