# MCP Server

```python
from largestack._core.mcp_streamable import StreamableHTTPServer, create_fastapi_app

server = StreamableHTTPServer(name="my-mcp")
server.register_tool("search", lambda q: f"results: {q}",
                     description="Search KB",
                     input_schema={"type": "object", "properties": {"q": {"type": "string"}}})

app = create_fastapi_app(server)
# Mount at /mcp endpoint
```
