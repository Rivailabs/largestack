# Largestack AI

Production-grade candidate Python framework for agentic AI.

## Why LARGESTACK

- **Typed decorator API** with full mypy/pyright support
- **15 guardrail layers** — PII, injection, toxicity, hallucination, OWASP coverage
- **6 native LLM providers** + **LiteLLM router** for 100+ more
- **Production-ready** — hash-chain audit, mTLS, RBAC, encryption out of box
- **Protocol-native** — MCP 2025-11-25, A2A v1.0, AG-UI 25 events, OTel GenAI

## Quick Install

```bash
pip install largestack
```

## Hello World

```python
from largestack.decorators import Agent, RunContext

agent = Agent("openai/gpt-4o-mini", instructions="Be helpful.")

@agent.tool_plain
def add(x: int, y: int) -> int:
    """Add numbers."""
    return x + y

result = await agent.run("What is 5 + 3?")
print(result.output)  # "5 + 3 = 8"
```

[Get started →](quickstart.md)

- [Competitive positioning](competitive-positioning.md)
