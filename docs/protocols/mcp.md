# MCP 2025-11-25

```python
from largestack._core.mcp_streamable import StreamableHTTPServer

server = StreamableHTTPServer(name="my-server")
server.register_tool("search", handler=lambda q: f"results for {q}")
```
