# Tutorial 1: Your First Agent

Build a working AI agent in under 2 minutes.

## Step 1: Install

```bash
pip install largestack[openai]
```

## Step 2: Set your API key

```bash
export LARGESTACK_OPENAI_API_KEY=<openai-api-key>
```

## Step 3: Create `agent.py`

```python
import asyncio
from largestack import Agent

agent = Agent(
    name="my-first-agent",
    instructions="You are a helpful assistant. Be concise.",
    llm="openai/gpt-4o-mini",
)

async def main():
    result = await agent.run("Explain quantum computing in one paragraph.")
    print(f"Response: {result.content}")
    print(f"Cost: ${result.total_cost:.4f}")
    print(f"Trace: {result.trace_id}")

asyncio.run(main())
```

## Step 4: Run it

```bash
python agent.py
```

You'll see the response, cost tracked automatically, and a trace ID for debugging.

## What happened under the hood

1. LARGESTACK loaded config from env vars and `largestack.yaml`
2. PII detection and injection guardrails ran on your input
3. The OpenAI provider sent your request with automatic retry
4. Cost was calculated from the pricing registry
5. A trace was recorded to `~/.largestack/traces.db`
6. An audit entry was written to `~/.largestack/audit.db`

## Next: [Add tools →](02_tools_and_functions.md)
