# Streaming Responses

```python
from largestack import Agent

agent = Agent(name="stream", llm="openai/gpt-4o-mini")
async for chunk in agent.run_stream("Tell a story"):
    print(chunk, end="", flush=True)
```
