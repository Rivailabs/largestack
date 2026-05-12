"""v0.12.0: Tests for A2A (Agent2Agent) Protocol adapter."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- AgentCard --------------------

def test_agent_card_to_dict_round_trip():
    from largestack._a2a import AgentCard, AgentSkill
    card = AgentCard(
        name="KYC Agent",
        description="Indian KYC and DPDP-compliant verification",
        url="https://kyc.example.com",
        skills=[AgentSkill(
            id="pan_verify",
            name="Verify PAN",
            description="Verifies a PAN against Signzy",
            tags=["kyc", "india"],
            examples=["Verify PAN AAACR1234C"],
        )],
        provider_name="RivaiLabs",
    )
    d = card.to_dict()
    assert d["name"] == "KYC Agent"
    assert d["skills"][0]["id"] == "pan_verify"
    rebuilt = AgentCard.from_dict(d)
    assert rebuilt.name == card.name
    assert len(rebuilt.skills) == 1
    assert rebuilt.skills[0].id == "pan_verify"


def test_agent_card_default_capabilities():
    from largestack._a2a import AgentCard
    card = AgentCard(
        name="x", description="y", url="z",
    )
    assert card.capabilities.streaming is False
    assert card.capabilities.state_transition_history is True


def test_agent_card_from_dict_tolerates_unknown_keys():
    from largestack._a2a import AgentCard
    d = {
        "name": "n", "description": "d", "url": "u",
        "future_field": "ignored",
    }
    card = AgentCard.from_dict(d)
    assert card.name == "n"


def test_agent_card_protocol_version_default():
    from largestack._a2a import AgentCard
    card = AgentCard(name="x", description="y", url="z")
    assert card.protocol_version == "0.3.0"


# -------------------- A2AMessage --------------------

def test_message_text_helper():
    from largestack._a2a import A2AMessage
    m = A2AMessage.text("user", "hello")
    assert m.role == "user"
    assert m.parts[0]["type"] == "text"
    assert m.parts[0]["text"] == "hello"


def test_message_get_text_concatenates_parts():
    from largestack._a2a import A2AMessage
    m = A2AMessage(role="agent", parts=[
        {"type": "text", "text": "hello"},
        {"type": "text", "text": "world"},
        {"type": "image", "url": "https://x"},  # not text
    ])
    assert m.get_text() == "hello\nworld"


# -------------------- A2ATask --------------------

def test_task_lifecycle_transitions():
    from largestack._a2a import A2ATask, A2AMessage
    t = A2ATask(id="t1")
    assert t.state == "submitted"
    t.transition("working")
    assert t.state == "working"
    t.add_message(A2AMessage.text("user", "do it"))
    assert len(t.messages) == 1
    t.transition("completed")
    assert t.state == "completed"


def test_task_transition_with_error():
    from largestack._a2a import A2ATask
    t = A2ATask(id="t1")
    t.transition("failed", error="LLM down")
    assert t.state == "failed"
    assert t.error == "LLM down"


def test_task_to_dict_serializes_messages():
    from largestack._a2a import A2ATask, A2AMessage
    t = A2ATask(id="t1")
    t.add_message(A2AMessage.text("user", "go"))
    d = t.to_dict()
    assert d["id"] == "t1"
    assert len(d["messages"]) == 1
    assert d["messages"][0]["role"] == "user"


# -------------------- A2AServer --------------------

@pytest.mark.asyncio
async def test_server_submit_task_success():
    from largestack._a2a import A2AServer, AgentCard

    async def handler(input_text: str, task) -> str:
        return f"echo: {input_text}"

    card = AgentCard(name="Echo", description="echo", url="x")
    server = A2AServer(card=card, handler=handler)
    task = await server.submit_task("hello")
    assert task.state == "completed"
    assert len(task.messages) == 2
    assert task.messages[0].role == "user"
    assert task.messages[1].role == "agent"
    assert "echo: hello" in task.messages[1].get_text()


@pytest.mark.asyncio
async def test_server_handler_failure_marks_task_failed():
    from largestack._a2a import A2AServer, AgentCard

    async def broken(input_text, task):
        raise RuntimeError("agent crashed")

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=broken,
    )
    task = await server.submit_task("anything")
    assert task.state == "failed"
    assert "agent crashed" in task.error


@pytest.mark.asyncio
async def test_server_get_task_returns_none_for_unknown():
    from largestack._a2a import A2AServer, AgentCard

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=lambda t, task: None,
    )
    assert await server.get_task("nope") is None


@pytest.mark.asyncio
async def test_server_purge_expired_tasks():
    import time as _t
    from largestack._a2a import A2AServer, AgentCard, A2ATask

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=lambda t, task: None,
        task_ttl_seconds=10,
    )
    # Inject an old completed task
    old = A2ATask(id="old", state="completed")
    old.updated_at = _t.time() - 100
    server._tasks["old"] = old
    purged = await server.purge_expired_tasks()
    assert purged == 1
    assert "old" not in server._tasks


# -------------------- A2AServer HTTP request handling --------------------

@pytest.mark.asyncio
async def test_handle_get_well_known_agent_json():
    from largestack._a2a import A2AServer, AgentCard

    async def handler(t, task):
        return ""

    card = AgentCard(name="Test", description="d", url="u")
    server = A2AServer(card=card, handler=handler)
    status, body = await server.handle_request(
        "GET", "/.well-known/agent.json", None,
    )
    assert status == 200
    assert body["name"] == "Test"


@pytest.mark.asyncio
async def test_handle_post_tasks_send_with_input_field():
    from largestack._a2a import A2AServer, AgentCard

    async def handler(t, task):
        return f"got: {t}"

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )
    status, body = await server.handle_request(
        "POST", "/tasks/send", {"input": "hello"},
    )
    assert status == 200
    assert body["state"] == "completed"
    # Last message should be the agent's reply
    assert "got: hello" in body["messages"][-1]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_handle_post_tasks_send_with_message_parts():
    """A2A spec accepts {message: {parts: [{type: text, text: ...}]}}"""
    from largestack._a2a import A2AServer, AgentCard

    async def handler(t, task):
        return f"got: {t}"

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )
    status, body = await server.handle_request(
        "POST", "/tasks/send",
        {"message": {"parts": [{"type": "text", "text": "from parts"}]}},
    )
    assert status == 200
    assert "got: from parts" in body["messages"][-1]["parts"][0]["text"]


@pytest.mark.asyncio
async def test_handle_post_tasks_send_rejects_empty_input():
    from largestack._a2a import A2AServer, AgentCard

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=lambda t, task: None,
    )
    status, body = await server.handle_request(
        "POST", "/tasks/send", {},
    )
    assert status == 400


@pytest.mark.asyncio
async def test_handle_get_specific_task():
    from largestack._a2a import A2AServer, AgentCard

    async def handler(t, task):
        return "done"

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=handler,
    )
    task = await server.submit_task("x", task_id="t-fixed")
    status, body = await server.handle_request(
        "GET", f"/tasks/{task.id}", None,
    )
    assert status == 200
    assert body["id"] == "t-fixed"


@pytest.mark.asyncio
async def test_handle_get_unknown_task_returns_404():
    from largestack._a2a import A2AServer, AgentCard

    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=lambda t, task: None,
    )
    status, body = await server.handle_request(
        "GET", "/tasks/nope", None,
    )
    assert status == 404


@pytest.mark.asyncio
async def test_handle_unknown_endpoint():
    from largestack._a2a import A2AServer, AgentCard
    server = A2AServer(
        card=AgentCard(name="x", description="y", url="z"),
        handler=lambda t, task: None,
    )
    status, _ = await server.handle_request(
        "GET", "/unknown", None,
    )
    assert status == 404


# -------------------- A2AClient (against in-process server) --------------------

@pytest.mark.asyncio
async def test_client_against_in_process_server():
    """Wire client → server via direct method calls (no HTTP)."""
    from largestack._a2a import A2AServer, A2AClient, AgentCard

    async def handler(input_text, task):
        return f"echo: {input_text}"

    server = A2AServer(
        card=AgentCard(
            name="Test", description="d", url="http://localhost:0",
        ),
        handler=handler,
    )

    # Mock the client's HTTP methods to call the server directly
    client = A2AClient(base_url="http://localhost:0")

    async def fake_post(path, body):
        return await server.handle_request("POST", path, body)
    async def fake_get(path):
        return await server.handle_request("GET", path, None)

    client._post_json = fake_post
    client._get_json = fake_get

    # Discover
    card = await client.discover()
    assert card.name == "Test"

    # Send task
    task = await client.send_task("hello world")
    assert task.state == "completed"


@pytest.mark.asyncio
async def test_client_get_task_returns_none_on_404():
    from largestack._a2a import A2AClient

    client = A2AClient(base_url="http://localhost:0")

    async def fake_get(path):
        return 404, {"error": "not found"}
    client._get_json = fake_get

    result = await client.get_task("nope")
    assert result is None


@pytest.mark.asyncio
async def test_client_send_task_raises_on_error():
    from largestack._a2a import A2AClient

    client = A2AClient(base_url="http://localhost:0")

    async def fake_post(path, body):
        return 500, {"error": "boom"}
    client._post_json = fake_post

    with pytest.raises(RuntimeError, match="send_task failed"):
        await client.send_task("hello")


# -------------------- expose_largestack_agent helper --------------------

@pytest.mark.asyncio
async def test_expose_largestack_agent_wraps_correctly():
    from largestack._a2a import expose_largestack_agent, AgentSkill

    largestack_agent = MagicMock()
    largestack_agent.run = AsyncMock(return_value=MagicMock(
        content="42",
    ))

    server = expose_largestack_agent(
        largestack_agent,
        name="Math",
        description="Does math",
        url="http://localhost:0",
        skills=[AgentSkill(id="add", name="Add", description="adds")],
    )

    task = await server.submit_task("what is 2+2?")
    assert task.state == "completed"
    assert "42" in task.messages[-1].get_text()
    assert server.card.skills[0].id == "add"


@pytest.mark.asyncio
async def test_expose_largestack_agent_default_provider():
    from largestack._a2a import expose_largestack_agent

    largestack_agent = MagicMock()
    largestack_agent.run = AsyncMock(return_value=MagicMock(content="x"))

    server = expose_largestack_agent(
        largestack_agent, name="x", description="y", url="z",
    )
    assert server.card.provider_name == "RivaiLabs"
    assert "rivailabs" in server.card.provider_url.lower()
