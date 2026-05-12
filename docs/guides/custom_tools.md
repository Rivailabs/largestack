# Guide: Building Custom Tools

## Basic Tool

```python
from largestack import tool

@tool
async def get_stock_price(symbol: str) -> str:
    """Get current stock price for a ticker symbol."""
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.get(f"https://api.example.com/stock/{symbol}")
        return f"{symbol}: ${r.json()['price']}"
```

Type hints → JSON Schema. Docstring → tool description. That's it.

## Tool Options

```python
@tool(timeout=60)              # 60s timeout (default: 30s)
@tool(retries=3)               # Auto-retry on failure
@tool(name="stock_lookup")     # Override function name
@tool(description="...")       # Override docstring
```

## Permissions

```python
agent = Agent(
    tools=[get_stock_price, write_file, shell_command],
    tool_permissions={
        "allow": ["get_stock_price", "write_file"],  # Only these allowed
        "deny": ["shell_command"],                     # Explicitly blocked
    }
)
```

## Convert RAG to Tool

```python
from largestack import create_rag

rag = create_rag(documents=my_docs)
search_tool = rag.as_tool()  # Returns @tool-decorated function
agent = Agent(tools=[search_tool])
```

## Idempotency

Tools are automatically idempotent — calling the same tool with the same parameters returns the cached result (SHA-256 keyed). This prevents duplicate API calls when the agent retries.
