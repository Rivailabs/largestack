"""Tests for MCP, A2A, AG-UI protocols."""
import sys, asyncio; sys.path.insert(0, ".")

def test_mcp_server_tool_call():
    from largestack._core.mcp_server import MCPServer
    srv = MCPServer("test")
    @srv.tool
    async def add(a: int, b: int) -> str: return str(a + b)
    r = asyncio.run(srv.handle_request({
        "jsonrpc": "2.0", "id": "1", "method": "tools/call",
        "params": {"name": "add", "arguments": {"a": 5, "b": 3}}}))
    assert "8" in r["result"]["content"][0]["text"]

def test_a2a_agent_card():
    from largestack._core.a2a_server import AgentCard
    card = AgentCard(name="test", description="A test agent")
    d = card.to_dict()
    assert d["name"] == "test" and "capabilities" in d

def test_agui_event():
    from largestack._core.ag_ui import AGUIEvent, AGUIEventType
    e = AGUIEvent(AGUIEventType.TEXT_MESSAGE_CONTENT, {"delta": "hello"}, "run-1")
    sse = e.to_sse()
    assert "TEXT_MESSAGE_CONTENT" in sse and "hello" in sse and "runId" in sse

def test_agui_all_event_types():
    from largestack._core.ag_ui import AGUIEventType
    types = [e.value for e in AGUIEventType]
    assert "RUN_STARTED" in types and "RUN_FINISHED" in types
    assert "TEXT_MESSAGE_CONTENT" in types and "TOOL_CALL_START" in types
    assert len(types) >= 13

def test_agui_server_routes():
    from largestack._core.ag_ui import AGUIServer
    from largestack import Agent
    agent = Agent(name="t", llm="deepseek/deepseek-chat", guardrails=None)
    app = AGUIServer(agent).create_app()
    paths = [getattr(r, 'path', '') for r in app.routes]
    assert "/ag-ui/runs" in paths and "/ag-ui/agent" in paths
