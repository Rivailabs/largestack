"""MCP server example — exposes tools to Cursor/Claude Code."""

from largestack._core.mcp_streamable import StreamableHTTPServer, create_fastapi_app

server = StreamableHTTPServer(name="my-mcp", version="1.0.0")


def search(query: str) -> str:
    return f"Found: {query}"


server.register_tool(
    "search",
    search,
    description="Search knowledge base",
    input_schema={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)

app = create_fastapi_app(server)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
