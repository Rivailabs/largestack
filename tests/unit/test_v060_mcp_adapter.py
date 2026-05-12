"""v0.6.0: Tests for MCP-as-a-Tool adapter.

Mocks MCPClient so we don't need a real MCP server.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_mcp_adapter_requires_url_or_command():
    from largestack._integrations.mcp_adapter import MCPToolAdapter
    with pytest.raises(ValueError, match="requires url or command"):
        MCPToolAdapter()


@pytest.mark.asyncio
async def test_mcp_adapter_wraps_tools_after_connect():
    """Connecting must produce one @tool callable per discovered MCP tool."""
    from largestack._integrations.mcp_adapter import MCPToolAdapter

    fake_tools = [
        {
            "name": "send_email",
            "description": "Send an email",
            "inputSchema": {
                "type": "object",
                "properties": {"to": {"type": "string"}, "subject": {"type": "string"}},
                "required": ["to", "subject"],
            },
        },
        {
            "name": "list_files",
            "description": "List files in a path",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    ]

    with patch("largestack._core.mcp_client.MCPClient") as MockClient:
        instance = MockClient.return_value
        instance.connect = AsyncMock(return_value=None)
        instance._tools = fake_tools

        adapter = MCPToolAdapter(url="http://localhost:8080/mcp")
        await adapter.connect()

    tools = adapter.get_tools()
    assert len(tools) == 2
    names = [t._tool_schema["name"] for t in tools]
    assert "send_email" in names
    assert "list_files" in names


@pytest.mark.asyncio
async def test_mcp_adapter_tool_call_proxies_to_mcp_client():
    """Calling a wrapped tool must forward args to MCPClient.call_tool."""
    from largestack._integrations.mcp_adapter import MCPToolAdapter

    with patch("largestack._core.mcp_client.MCPClient") as MockClient:
        instance = MockClient.return_value
        instance.connect = AsyncMock(return_value=None)
        instance.call_tool = AsyncMock(return_value="email sent")
        instance._tools = [
            {"name": "send_email", "description": "send", "inputSchema": {}},
        ]

        adapter = MCPToolAdapter(url="http://example.com/mcp")
        await adapter.connect()
        send_email = adapter.get_tools()[0]
        result = await send_email(to="a@b.com", subject="Hi")

    assert result == "email sent"
    instance.call_tool.assert_awaited_once_with(
        "send_email", {"to": "a@b.com", "subject": "Hi"}
    )


@pytest.mark.asyncio
async def test_mcp_adapter_tool_call_returns_error_string_on_exception():
    """If MCPClient raises, the wrapper must return an error string,
    not propagate (so the agent loop survives)."""
    from largestack._integrations.mcp_adapter import MCPToolAdapter

    with patch("largestack._core.mcp_client.MCPClient") as MockClient:
        instance = MockClient.return_value
        instance.connect = AsyncMock(return_value=None)
        instance.call_tool = AsyncMock(side_effect=RuntimeError("server down"))
        instance._tools = [
            {"name": "broken", "description": "x", "inputSchema": {}},
        ]
        adapter = MCPToolAdapter(url="http://x")
        await adapter.connect()

    result = await adapter.get_tools()[0]()
    assert "MCP tool broken failed" in result
    assert "server down" in result


@pytest.mark.asyncio
async def test_mcp_adapter_attaches_mcp_schema_to_wrapped_tool():
    """The MCP inputSchema must be carried to the wrapped tool so the
    LLM sees correct parameter types."""
    from largestack._integrations.mcp_adapter import MCPToolAdapter

    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "depth": {"type": "integer"}},
        "required": ["path"],
    }

    with patch("largestack._core.mcp_client.MCPClient") as MockClient:
        instance = MockClient.return_value
        instance.connect = AsyncMock(return_value=None)
        instance._tools = [
            {"name": "list_files", "description": "...", "inputSchema": schema},
        ]
        adapter = MCPToolAdapter(url="http://x")
        await adapter.connect()

    t = adapter.get_tools()[0]
    assert hasattr(t, "_mcp_schema")
    assert t._mcp_schema == schema


@pytest.mark.asyncio
async def test_mcp_adapter_async_context_manager():
    """``async with MCPToolAdapter(...)`` must connect on enter, close on exit."""
    from largestack._integrations.mcp_adapter import MCPToolAdapter

    with patch("largestack._core.mcp_client.MCPClient") as MockClient:
        instance = MockClient.return_value
        # MCPClient instances don't have an `aclose` method — only
        # `_client.aclose` (httpx) or `_process.terminate` (stdio).
        # Configure spec to drop magic auto-attrs.
        instance.connect = AsyncMock(return_value=None)
        instance._tools = []
        # Simulate the HTTP transport: instance._client.aclose() exists
        http_client = MagicMock()
        http_client.aclose = AsyncMock()
        instance._client = http_client
        instance._process = None
        # Remove the auto-generated aclose so the adapter falls through
        # to the _client.aclose() branch (HTTP path).
        del instance.aclose

        async with MCPToolAdapter(url="http://x") as adapter:
            assert adapter.get_tools() == []
            instance.connect.assert_awaited_once()

        # Close must have been called on the http subclient
        http_client.aclose.assert_awaited_once()
