# Customer Support Bot

```python
from largestack import Agent, create_rag, tool

@tool
async def create_ticket(email: str, issue: str) -> str:
    """Create support ticket."""
    return f"TICKET-{hash(email)}"

rag = create_rag(documents=["faq.md"])
agent = Agent(name="support", llm="deepseek/deepseek-chat",
              tools=[rag.as_tool(), create_ticket])
```
