"""MCP Server Builder — create MCP servers from LARGESTACK tools.

Decorators: @mcp_tool, @mcp_resource, @mcp_prompt
"""

from __future__ import annotations
import json, asyncio, inspect, sys
from typing import Any, Callable


class MCPServer:
    """Build MCP servers exposing LARGESTACK tools."""

    def __init__(self, name: str = "largestack-mcp", version: str = "0.1.0"):
        self.name = name
        self.version = version
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, dict] = {}
        self._prompts: dict[str, dict] = {}

    def tool(self, fn: Callable = None, *, name: str = None, description: str = None):
        """Register a function as an MCP tool."""

        def decorator(f):
            from largestack._core.tools import ToolRegistry

            schema = ToolRegistry._gen(f)
            tname = name or schema["name"]
            self._tools[tname] = {
                "handler": f,
                "schema": schema,
                "description": description or schema["description"],
            }
            return f

        return decorator(fn) if fn else decorator

    def resource(self, uri: str, name: str = "", description: str = ""):
        """Register an MCP resource."""

        def decorator(fn):
            self._resources[uri] = {"handler": fn, "name": name or uri, "description": description}
            return fn

        return decorator

    def prompt(self, name: str, description: str = ""):
        """Register an MCP prompt template."""

        def decorator(fn):
            self._prompts[name] = {"handler": fn, "description": description}
            return fn

        return decorator

    async def handle_request(self, request: dict) -> dict:
        """Handle a JSON-RPC 2.0 request."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "initialize":
            return self._response(
                req_id,
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            )
        elif method == "tools/list":
            tools = [
                {
                    "name": n,
                    "description": d["description"],
                    "inputSchema": d["schema"].get("parameters", {}),
                }
                for n, d in self._tools.items()
            ]
            return self._response(req_id, {"tools": tools})
        elif method == "tools/call":
            return await self._call_tool(req_id, params)
        elif method == "resources/list":
            resources = [
                {"uri": u, "name": d["name"], "description": d["description"]}
                for u, d in self._resources.items()
            ]
            return self._response(req_id, {"resources": resources})

        return self._error(req_id, -32601, f"Method not found: {method}")

    async def _call_tool(self, req_id, params) -> dict:
        name = params.get("name", "")
        args = params.get("arguments", {})
        tool = self._tools.get(name)
        if not tool:
            return self._error(req_id, -32602, f"Tool not found: {name}")
        try:
            fn = tool["handler"]
            result = await fn(**args) if asyncio.iscoroutinefunction(fn) else fn(**args)
            return self._response(req_id, {"content": [{"type": "text", "text": str(result)}]})
        except Exception as e:
            return self._error(req_id, -32000, str(e))

    def _response(self, req_id, result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id, code, msg):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": msg}}

    async def run_stdio(self):
        """Run server using stdio transport."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(
            writer_transport, writer_protocol, reader, asyncio.get_event_loop()
        )

        while True:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line.decode())
            response = await self.handle_request(request)
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
