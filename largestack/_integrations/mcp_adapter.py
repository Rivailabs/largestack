"""MCP-as-a-Tool adapter (v0.6.0).

Lets a LARGESTACK agent use any MCP server's tools as if they were native
LARGESTACK @tool functions. This is the **single most valuable integration
feature** since the MCP standard was finalized — instead of writing
N adapters for N services, you write 1 adapter (this one) and any
MCP-compatible server becomes available.

Usage:

    from largestack._integrations.mcp_adapter import MCPToolAdapter
    from largestack import Agent

    adapter = MCPToolAdapter(url="http://localhost:8080/mcp")
    await adapter.connect()
    tools = adapter.get_tools()  # list of @tool-decorated callables

    agent = Agent(name="ops", llm="...", tools=tools)
    await adapter.aclose()  # when done

Or via convenience:

    async with MCPToolAdapter(url="...") as adapter:
        agent = Agent(..., tools=adapter.get_tools())
        await agent.run("...")

Notes:
- The adapter caches the tool list at connect-time. Servers that add tools
  later require reconnecting.
- Each MCP tool maps to a LARGESTACK tool with the SAME name. If your server
  exposes ``send_email``, your agent calls ``send_email`` directly.
- Errors from the MCP server are propagated as the tool's return string.
- The agent never sees the underlying transport — stdio or HTTP — it just
  calls the tool and gets a string back.
"""

from __future__ import annotations
import logging
from typing import Any, Callable

from largestack._core.tools import tool

log = logging.getLogger("largestack.mcp_adapter")


class MCPToolAdapter:
    """Wraps an MCP server connection as a list of LARGESTACK @tool callables."""

    def __init__(self, url: str | None = None, command: str | None = None):
        """
        Args:
            url: HTTP URL of the MCP server (one of url or command required).
            command: Local command to spawn an MCP server over stdio
                (e.g. "uvx mcp-server-fetch").
        """
        if not (url or command):
            raise ValueError("MCPToolAdapter requires url or command")
        from largestack._core.mcp_client import MCPClient

        self._client = MCPClient(url=url, command=command)
        self._tools: list[Callable] = []

    async def connect(self) -> None:
        """Connect and discover tools. Builds the @tool wrappers."""
        await self._client.connect()
        self._tools = [self._wrap(t) for t in self._client._tools]
        log.info(f"MCP adapter ready: {len(self._tools)} tools")

    async def aclose(self) -> None:
        """Disconnect from the MCP server."""
        if hasattr(self._client, "aclose"):
            await self._client.aclose()
        elif hasattr(self._client, "_client") and self._client._client is not None:
            await self._client._client.aclose()
        elif hasattr(self._client, "_process") and self._client._process is not None:
            self._client._process.terminate()

    def get_tools(self) -> list[Callable]:
        """Return the list of @tool-decorated callables. Use as agent tools."""
        return list(self._tools)

    def _wrap(self, mcp_tool: dict) -> Callable:
        """Convert one MCP tool descriptor into a LARGESTACK @tool callable.

        MCP tool format:
            {"name": "send_email", "description": "...",
             "inputSchema": {"type": "object", "properties": {...}}}
        """
        name = mcp_tool.get("name", "mcp_tool")
        desc = mcp_tool.get("description", f"MCP tool {name}")
        client = self._client

        # We can't dynamically generate functions with arbitrary signatures
        # cleanly, so the wrapper takes ``**kwargs`` and forwards them.
        # The LLM-facing schema is still derived from MCP inputSchema below.
        @tool(timeout=60, name=name, description=desc)
        async def _bridge(**arguments) -> str:
            try:
                result = await client.call_tool(name, arguments)
                return result if isinstance(result, str) else str(result)
            except Exception as e:
                return f"MCP tool {name} failed: {e}"

        # Attach the MCP schema directly so the agent's tool registry
        # advertises the correct parameter list to the LLM, not just **kwargs.
        schema = mcp_tool.get("inputSchema", {})
        if schema and isinstance(schema, dict):
            _bridge._mcp_schema = schema  # type: ignore
            _bridge.parameters = schema  # type: ignore

        return _bridge

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()
