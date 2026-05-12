# Structured Output (Pydantic)

```python
from pydantic import BaseModel
from largestack import Agent

class Review(BaseModel):
    rating: int
    summary: str

agent = Agent(name="reviewer", llm="openai/gpt-4o")
result = await agent.run("Review Inception", response_model=Review)
print(result.content.rating)
```
