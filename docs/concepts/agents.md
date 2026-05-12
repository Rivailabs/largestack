# Agents

```python
from dataclasses import dataclass
from largestack.decorators import Agent, RunContext

@dataclass
class Deps:
    db: object
    user_id: str

agent = Agent[Deps, str](
    "openai/gpt-4o", deps_type=Deps,
    instructions="You are a support agent.",
)
```
