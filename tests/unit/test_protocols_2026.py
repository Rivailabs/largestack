"""Tests for MCP 2025-11-25, A2A v1.0, AG-UI 25 events."""
import asyncio, sys; sys.path.insert(0, ".")

def test_mcp_streamable_server():
    from largestack._core.mcp_streamable import StreamableHTTPServer, PROTOCOL_VERSION
    server = StreamableHTTPServer(name="test")
    server.register_tool("search", lambda q: f"results: {q}",
                          description="Search",
                          input_schema={"type": "object", "properties": {"q": {"type": "string"}}})
    assert PROTOCOL_VERSION == "2025-11-25"
    assert server.stats['tools_count'] == 1
    assert server.stats['protocol_version'] == "2025-11-25"

def test_mcp_initialize():
    from largestack._core.mcp_streamable import StreamableHTTPServer
    server = StreamableHTTPServer(name="test")
    req = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}'
    result = asyncio.run(server.handle_request(req))
    assert result['result']['protocolVersion'] == "2025-11-25"
    assert 'serverInfo' in result['result']

def test_mcp_tools_list():
    from largestack._core.mcp_streamable import StreamableHTTPServer
    server = StreamableHTTPServer()
    server.register_tool("foo", lambda: "ok", description="Foo tool")
    req = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
    result = asyncio.run(server.handle_request(req))
    tools = result['result']['tools']
    assert len(tools) == 1
    assert tools[0]['name'] == 'foo'

def test_mcp_origin_validation():
    from largestack._core.mcp_streamable import StreamableHTTPServer
    server = StreamableHTTPServer(allowed_origins=["https://app.com"])
    assert server.validate_origin("https://app.com") is True
    assert server.validate_origin("https://evil.com") is False

def test_a2a_v1_states():
    from largestack._core.a2a_v1 import TaskState
    assert TaskState.SUBMITTED.value == "SUBMITTED"  # SCREAMING_SNAKE_CASE
    assert TaskState.WORKING.value == "WORKING"
    assert TaskState.COMPLETED.value == "COMPLETED"

def test_a2a_v1_agent_card():
    from largestack._core.a2a_v1 import A2AServer, A2A_VERSION
    server = A2AServer(name="test", description="test agent", url="http://localhost/a2a")
    server.add_skill("search", "Search", "Search documents", tags=["search"])
    card = server.get_agent_card()
    assert card['name'] == "test"
    assert len(card['skills']) == 1
    assert A2A_VERSION == "1.0"

def test_a2a_v1_signed_card():
    from largestack._core.a2a_v1 import A2AServer
    server = A2AServer(name="test", description="d", url="x", signing_key=b"secret_key_bytes")
    card = server.get_agent_card()
    assert '_signature' in card

def test_agui_event_count():
    from largestack._core.agui_v1 import EventType
    # Should have at least 21 unique event types (25 with 4 deprecated)
    assert len(set(e.value for e in EventType)) >= 21

def test_agui_emitter():
    from largestack._core.agui_v1 import AGUIEmitter, EventType
    em = AGUIEmitter()
    started = em.run_started()
    assert started.type == EventType.RUN_STARTED
    assert started.thread_id

def test_agui_text_message_lifecycle():
    from largestack._core.agui_v1 import AGUIEmitter, EventType
    em = AGUIEmitter()
    events = em.text_message("hello")
    assert len(events) == 3
    assert events[0].type == EventType.TEXT_MESSAGE_START
    assert events[1].type == EventType.TEXT_MESSAGE_CONTENT
    assert events[2].type == EventType.TEXT_MESSAGE_END

def test_agui_state_delta_json_patch():
    from largestack._core.agui_v1 import AGUIEmitter, EventType
    em = AGUIEmitter()
    delta = em.state_delta([{"op": "replace", "path": "/x", "value": 5}])
    assert delta.type == EventType.STATE_DELTA
    assert delta.delta[0]['op'] == 'replace'

def test_agui_sse_format():
    from largestack._core.agui_v1 import AGUIEmitter
    em = AGUIEmitter()
    started = em.run_started()
    sse = started.to_sse()
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    assert "RUN_STARTED" in sse
