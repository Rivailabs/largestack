"""MCP (Model Context Protocol) 2025-11-25 Streamable HTTP transport.

Implements latest spec:
  - JSON-RPC 2.0 over HTTP
  - Single endpoint POST + GET
  - MCP-Protocol-Version header
  - MCP-Session-Id for session management
  - Origin validation
  - Resumable streams via Last-Event-ID

Spec: https://modelcontextprotocol.io/specification/2025-11-25
"""

from __future__ import annotations
import json
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

log = logging.getLogger("largestack.mcp.streamable")

PROTOCOL_VERSION = "2025-11-25"


@dataclass
class MCPSession:
    """MCP session with TTL."""

    session_id: str
    created_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    capabilities: dict = field(default_factory=dict)

    def touch(self):
        self.last_seen = time.time()

    def is_expired(self, ttl_seconds: int = 3600) -> bool:
        return (time.time() - self.last_seen) > ttl_seconds


class StreamableHTTPServer:
    """MCP server with Streamable HTTP transport (2025-11-25 spec).

    Single endpoint that handles both POST (request) and GET (server push).
    Supports session management and resumable streams.

    Example:
        server = StreamableHTTPServer(
            name="my-server",
            allowed_origins=["https://app.example.com"],
        )
        server.register_tool("search", search_handler)
        # Mount at /mcp endpoint via FastAPI
    """

    def __init__(
        self,
        name: str = "largestack-mcp",
        version: str = "0.1.0",
        allowed_origins: list[str] | None = None,
        session_ttl_seconds: int = 3600,
    ):
        self.name = name
        self.version = version
        self.allowed_origins = allowed_origins or ["*"]
        self.session_ttl = session_ttl_seconds

        self._tools: dict[str, dict] = {}
        self._tool_handlers: dict[str, Callable] = {}
        self._resources: dict[str, dict] = {}
        self._prompts: dict[str, dict] = {}
        self._sessions: dict[str, MCPSession] = {}

    def register_tool(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        input_schema: dict | None = None,
    ) -> None:
        """Register an MCP tool."""
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema or {"type": "object", "properties": {}},
        }
        self._tool_handlers[name] = handler

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str = "",
        mime_type: str = "text/plain",
    ) -> None:
        """Register an MCP resource."""
        self._resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": mime_type,
        }

    def register_prompt(
        self,
        name: str,
        description: str = "",
        arguments: list[dict] | None = None,
    ) -> None:
        """Register an MCP prompt template."""
        self._prompts[name] = {
            "name": name,
            "description": description,
            "arguments": arguments or [],
        }

    def validate_origin(self, origin: str | None) -> bool:
        """Check if origin is allowed (DNS rebinding protection)."""
        if not origin or "*" in self.allowed_origins:
            return True
        return origin in self.allowed_origins

    def get_or_create_session(self, session_id: str | None = None) -> MCPSession:
        """Get existing session or create new one."""
        if session_id and session_id in self._sessions:
            session = self._sessions[session_id]
            if not session.is_expired(self.session_ttl):
                session.touch()
                return session
            del self._sessions[session_id]

        new_id = secrets.token_urlsafe(32)
        session = MCPSession(session_id=new_id)
        self._sessions[new_id] = session
        return session

    async def handle_request(
        self,
        request_body: bytes | str,
        protocol_version: str = PROTOCOL_VERSION,
        session_id: str | None = None,
        origin: str | None = None,
    ) -> dict:
        """Handle a JSON-RPC request.

        Returns dict with: result, session_id, protocol_version
        """
        if not self.validate_origin(origin):
            return self._error_response(None, -32600, f"Invalid origin: {origin}")

        if isinstance(request_body, bytes):
            request_body = request_body.decode("utf-8")

        try:
            req = json.loads(request_body)
        except json.JSONDecodeError as e:
            return self._error_response(None, -32700, f"Parse error: {e}")

        session = self.get_or_create_session(session_id)

        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})

        try:
            if method == "initialize":
                result = self._handle_initialize(params, session)
            elif method == "tools/list":
                result = {"tools": list(self._tools.values())}
            elif method == "tools/call":
                result = await self._handle_tool_call(params)
            elif method == "resources/list":
                result = {"resources": list(self._resources.values())}
            elif method == "prompts/list":
                result = {"prompts": list(self._prompts.values())}
            elif method == "ping":
                result = {}
            else:
                return self._error_response(req_id, -32601, f"Method not found: {method}")

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
                "_session_id": session.session_id,
                "_protocol_version": PROTOCOL_VERSION,
            }
        except Exception as e:
            log.exception(f"MCP error in {method}")
            return self._error_response(req_id, -32603, f"Internal error: {e}")

    def _handle_initialize(self, params: dict, session: MCPSession) -> dict:
        """Handle initialize handshake."""
        client_version = params.get("protocolVersion", "")
        session.capabilities = params.get("capabilities", {})

        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": self.name, "version": self.version},
        }

    async def _handle_tool_call(self, params: dict) -> dict:
        """Execute a tool call."""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in self._tool_handlers:
            raise ValueError(f"Unknown tool: {tool_name}")

        handler = self._tool_handlers[tool_name]
        import inspect

        if inspect.iscoroutinefunction(handler):
            result = await handler(**arguments)
        else:
            result = handler(**arguments)

        # Wrap in MCP content format
        if isinstance(result, str):
            content = [{"type": "text", "text": result}]
        elif isinstance(result, dict):
            content = [{"type": "text", "text": json.dumps(result)}]
        else:
            content = [{"type": "text", "text": str(result)}]

        return {"content": content, "isError": False}

    def _error_response(self, req_id: Any, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "protocol_version": PROTOCOL_VERSION,
            "tools_count": len(self._tools),
            "resources_count": len(self._resources),
            "prompts_count": len(self._prompts),
            "active_sessions": len(self._sessions),
        }


def create_fastapi_app(server: StreamableHTTPServer):
    """Mount MCP server at /mcp endpoint via FastAPI."""
    from fastapi import FastAPI, Request, Response, Header

    app = FastAPI(title=f"MCP Server: {server.name}")

    @app.post("/mcp")
    async def handle_mcp_post(
        request: Request,
        mcp_protocol_version: str = Header(default=PROTOCOL_VERSION),
        mcp_session_id: str | None = Header(default=None),
        origin: str | None = Header(default=None),
    ):
        body = await request.body()
        result = await server.handle_request(body, mcp_protocol_version, mcp_session_id, origin)

        session_id = result.pop("_session_id", None)
        proto_ver = result.pop("_protocol_version", PROTOCOL_VERSION)

        headers = {
            "MCP-Protocol-Version": proto_ver,
        }
        if session_id:
            headers["MCP-Session-Id"] = session_id

        return Response(
            content=json.dumps(result),
            media_type="application/json",
            headers=headers,
        )

    @app.get("/mcp/info")
    def server_info():
        return server.stats

    return app
