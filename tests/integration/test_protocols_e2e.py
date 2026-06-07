"""A2A v1.0 + AG-UI v1 end-to-end tests (v0.4.0).

The v0.3.x reviewers flagged that the protocol implementations had thin
test coverage. This file fills that gap: full client/server round-trips
through the actual JSON-RPC + SSE machinery, plus enum/dataclass shape
verification.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# A2A v1.0
# ===========================================================================


class TestA2AAgentCard:
    """The agent card is what other agents discover us by — every field
    matters."""

    def test_agent_card_default_shape(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(name="x", description="y", version="1.0")
        card = s.get_agent_card()
        # All required fields per A2A v1.0 spec
        for k in (
            "name",
            "description",
            "version",
            "url",
            "capabilities",
            "authentication",
            "defaultInputModes",
            "defaultOutputModes",
            "skills",
        ):
            assert k in card, f"missing card key: {k}"

    def test_agent_card_capabilities_streaming_default_true(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(name="x", description="y", version="1.0")
        card = s.get_agent_card()
        assert card["capabilities"]["streaming"] is True

    def test_agent_card_signed_when_key_provided(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(
            name="x",
            description="y",
            version="1.0",
            signing_key=b"secret-key-32-bytes-long-padding",
        )
        card = s.get_agent_card()
        assert "_signature" in card
        assert len(card["_signature"]) == 64  # sha256 hex

    def test_agent_card_unsigned_when_no_key(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(name="x", description="y", version="1.0")
        card = s.get_agent_card()
        assert "_signature" not in card

    def test_skills_added_appear_on_card(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(name="x", description="y", version="1.0")
        s.add_skill("calc", "Calculator", "Add numbers", tags=["math"])
        s.add_skill("translate", "Translator", "Translate text", tags=["nlp"])
        card = s.get_agent_card()
        assert len(card["skills"]) == 2
        ids = [sk["id"] for sk in card["skills"]]
        assert "calc" in ids and "translate" in ids


class TestA2ATaskLifecycle:
    """Full task lifecycle — the core protocol contract."""

    @pytest.mark.asyncio
    async def test_message_send_creates_task_and_completes(self):
        from largestack._core.a2a_v1 import A2AServer, Task, TaskState

        async def handler(task: Task) -> Task:
            task.artifacts.append({"type": "text", "content": "echoed"})
            return task

        s = A2AServer(name="t", description="d", version="1.0")
        s.register_handler(handler)
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": {"role": "user", "content": "hi"}},
        }
        resp = await s.handle_request(req)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert "result" in resp
        result = resp["result"]
        assert result["status"]["state"] == TaskState.COMPLETED.value
        assert len(result["artifacts"]) == 1
        assert result["artifacts"][0]["content"] == "echoed"

    @pytest.mark.asyncio
    async def test_handler_exception_marks_task_failed(self):
        from largestack._core.a2a_v1 import A2AServer, Task, TaskState

        async def bad_handler(task: Task) -> Task:
            raise RuntimeError("boom")

        s = A2AServer(name="t", description="d", version="1.0")
        s.register_handler(bad_handler)
        resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"role": "user", "content": "fail"}},
            }
        )
        result = resp["result"]
        assert result["status"]["state"] == TaskState.FAILED.value
        assert result["error"]["code"] == 13
        assert "boom" in result["error"]["message"]

    @pytest.mark.asyncio
    async def test_tasks_get_returns_existing_task(self):
        from largestack._core.a2a_v1 import A2AServer, Task

        s = A2AServer(name="t", description="d", version="1.0")
        s.register_handler(lambda t: t)

        # Send a message first to create a task
        send_resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"role": "user", "content": "hi"}},
            }
        )
        task_id = send_resp["result"]["id"]

        # Now fetch it
        get_resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tasks/get",
                "params": {"id": task_id},
            }
        )
        assert get_resp["result"]["id"] == task_id

    @pytest.mark.asyncio
    async def test_tasks_cancel_transitions_state(self):
        from largestack._core.a2a_v1 import A2AServer, TaskState

        s = A2AServer(name="t", description="d", version="1.0")
        s.register_handler(lambda t: t)

        send_resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"role": "user", "content": "hi"}},
            }
        )
        task_id = send_resp["result"]["id"]

        cancel_resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tasks/cancel",
                "params": {"id": task_id},
            }
        )
        assert cancel_resp["result"]["status"]["state"] == TaskState.CANCELED.value

    @pytest.mark.asyncio
    async def test_unknown_method_returns_jsonrpc_error(self):
        from largestack._core.a2a_v1 import A2AServer

        s = A2AServer(name="t", description="d", version="1.0")
        resp = await s.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "unknown/method",
                "params": {},
            }
        )
        assert "error" in resp
        assert resp["error"]["code"] == 5
        assert "Method not found" in resp["error"]["message"]


class TestA2AFastAPIServer:
    """End-to-end through the FastAPI layer."""

    def test_well_known_agent_card_endpoint(self):
        from largestack._core.a2a_v1 import A2AServer, create_fastapi_app

        s = A2AServer(
            name="my-agent", description="d", version="1.0", url="http://localhost:8000/a2a"
        )
        app = create_fastapi_app(s)
        client = TestClient(app)
        r = client.get("/.well-known/agent-card.json")
        assert r.status_code == 200
        assert r.json()["name"] == "my-agent"

    def test_a2a_jsonrpc_post_endpoint(self):
        from largestack._core.a2a_v1 import A2AServer, Task, create_fastapi_app

        async def handler(task: Task) -> Task:
            return task

        s = A2AServer(name="x", description="y", version="1.0")
        s.register_handler(handler)
        app = create_fastapi_app(s)
        client = TestClient(app)
        r = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"role": "user", "content": "test"}},
            },
        )
        assert r.status_code == 200
        assert "result" in r.json()

    def test_info_endpoint_returns_protocol_version(self):
        from largestack._core.a2a_v1 import A2AServer, create_fastapi_app

        s = A2AServer(name="x", description="y", version="1.0")
        app = create_fastapi_app(s)
        client = TestClient(app)
        r = client.get("/a2a/info")
        assert r.status_code == 200
        body = r.json()
        assert body["protocol_version"] == "1.0"
        assert body["tasks_total"] == 0


class TestA2AEnumValues:
    """SCREAMING_SNAKE_CASE — A2A v1.0 changed from kebab-case in v0.x.
    Regression-guard the change so we don't accidentally break clients."""

    def test_task_states_are_screaming_snake_case(self):
        from largestack._core.a2a_v1 import TaskState

        expected = {
            "SUBMITTED",
            "WORKING",
            "INPUT_REQUIRED",
            "COMPLETED",
            "FAILED",
            "CANCELED",
        }
        actual = {s.value for s in TaskState}
        assert actual == expected, f"missing or extra states: {actual ^ expected}"


# ===========================================================================
# AG-UI v1
# ===========================================================================


class TestAGUIEvents:
    """Each event type round-trips through the SSE serialization."""

    def test_event_types_count_at_least_25(self):
        from largestack._core.agui_v1 import EventType

        # Spec says 25; project has 25 + 2 deprecated aliases
        assert len(EventType) >= 25

    def test_run_started_emits_correct_sse(self):
        from largestack._core.agui_v1 import RunStarted, EventType

        ev = RunStarted(thread_id="T1", run_id="R1")
        sse = ev.to_sse()
        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")
        body = json.loads(sse[6:].strip())
        assert body["type"] == EventType.RUN_STARTED.value
        assert body["thread_id"] == "T1"
        assert body["run_id"] == "R1"
        assert "timestamp" in body

    def test_text_message_content_preserves_delta(self):
        from largestack._core.agui_v1 import TextMessageContent

        ev = TextMessageContent(message_id="M1", delta="hello world")
        body = json.loads(ev.to_sse()[6:].strip())
        assert body["delta"] == "hello world"
        assert body["message_id"] == "M1"

    def test_tool_call_lifecycle_events(self):
        """Start → args → end is the tool call sequence on the wire."""
        from largestack._core.agui_v1 import ToolCallStart, ToolCallArgs, ToolCallEnd

        s = ToolCallStart(tool_call_id="tc1", tool_call_name="search", parent_message_id="m1")
        a = ToolCallArgs(tool_call_id="tc1", delta='{"query":"x"}')
        e = ToolCallEnd(tool_call_id="tc1")
        for ev in (s, a, e):
            body = json.loads(ev.to_sse()[6:].strip())
            assert body["tool_call_id"] == "tc1"

    def test_state_delta_uses_json_patch_shape(self):
        from largestack._core.agui_v1 import StateDelta

        # JSON Patch (RFC 6902): list of {op, path, value}
        patch = [{"op": "replace", "path": "/counter", "value": 5}]
        ev = StateDelta(delta=patch)
        body = json.loads(ev.to_sse()[6:].strip())
        assert body["delta"] == patch

    def test_run_error_carries_message_and_code(self):
        from largestack._core.agui_v1 import RunError

        ev = RunError(thread_id="T", run_id="R", message="bad", code="E_BAD")
        body = json.loads(ev.to_sse()[6:].strip())
        assert body["message"] == "bad"
        assert body["code"] == "E_BAD"

    def test_event_serialization_handles_unicode(self):
        from largestack._core.agui_v1 import TextMessageContent

        ev = TextMessageContent(message_id="m", delta="héllo 日本語 🚀")
        body = json.loads(ev.to_sse()[6:].strip())
        assert body["delta"] == "héllo 日本語 🚀"


class TestAGUIEventCategoryCoverage:
    """Make sure every spec category has at least one importable type."""

    def test_lifecycle_events_importable(self):
        from largestack._core.agui_v1 import (
            RunStarted,
            RunFinished,
            RunError,
        )

        # If all 3 import without error, the dataclass shapes hold.
        assert all(c.__name__ for c in (RunStarted, RunFinished, RunError))

    def test_text_events_importable(self):
        from largestack._core.agui_v1 import (
            TextMessageStart,
            TextMessageContent,
            TextMessageEnd,
        )

        assert all(c.__name__ for c in (TextMessageStart, TextMessageContent, TextMessageEnd))

    def test_tool_call_events_importable(self):
        from largestack._core.agui_v1 import (
            ToolCallStart,
            ToolCallArgs,
            ToolCallEnd,
            ToolCallResult,
        )

        assert all(c.__name__ for c in (ToolCallStart, ToolCallArgs, ToolCallEnd, ToolCallResult))

    def test_state_events_importable(self):
        from largestack._core.agui_v1 import StateSnapshot, StateDelta

        assert all(c.__name__ for c in (StateSnapshot, StateDelta))

    def test_reasoning_events_importable(self):
        from largestack._core.agui_v1 import ReasoningStart, ReasoningContent

        assert all(c.__name__ for c in (ReasoningStart, ReasoningContent))


# ===========================================================================
# Cross-protocol guard — make sure they don't conflict at import time
# ===========================================================================


def test_both_protocols_coexist():
    """Both protocol modules import in the same session without name clashes."""
    from largestack._core import a2a_v1, agui_v1

    # Sanity: top-level public names differ
    a2a_names = {n for n in dir(a2a_v1) if not n.startswith("_")}
    agui_names = {n for n in dir(agui_v1) if not n.startswith("_")}
    overlap = a2a_names & agui_names
    # Expected overlaps are stdlib / typing / utility imports + dataclass
    # helpers + the protocol's own factory functions exported by both.
    expected = {
        "asdict",
        "dataclass",
        "field",
        "Enum",
        "asyncio",
        "json",
        "logging",
        "time",
        "uuid",
        "Any",
        "AsyncIterator",
        "Callable",
        "annotations",
        "log",
        "create_fastapi_app",
    }
    real_overlap = overlap - expected
    assert not real_overlap, f"unexpected name overlap: {real_overlap}"
