# Guardrails

15 layers protecting against PII leaks, prompt injection, toxicity, hallucination.

```python
from largestack import Agent, create_guardrails

agent = Agent(
    name="safe",
    llm="openai/gpt-4o-mini",
    guardrails=create_guardrails(pii=True, injection=True, toxicity=True),
)
```

Or named list:
```python
agent = Agent(guardrails=["pii", "injection", "toxicity", "hallucination"])
```
