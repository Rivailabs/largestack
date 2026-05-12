"""AG-UI (Agent-User Interaction Protocol) — streaming events to frontends.

Completes the protocol trifecta: MCP (tools) + A2A (agents) + AG-UI (frontend).
No other framework has all three.

AG-UI streams ~16 event types over SSE:
  LIFECYCLE: run_started, run_finished, run_error
  TEXT:      text_message_start, text_message_content, text_message_end
  TOOL:     tool_call_start, tool_call_args, tool_call_end
  STATE:    state_snapshot, state_delta
  CUSTOM:   custom

Spec: https://docs.ag-ui.com
"""
from __future__ import annotations
import json, time, uuid, asyncio, logging
from typing import Any, AsyncIterator
from enum import Enum

from fastapi import Request

log = logging.getLogger("largestack.ag_ui")

class AGUIEventType(str, Enum):
    """All 26 AG-UI event types per specification."""
    # Lifecycle (5)
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"
    # Text messages (3)
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    # Tool calls (4)
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    # State management (4)
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"
    ACTIVITY_SNAPSHOT = "ACTIVITY_SNAPSHOT"
    ACTIVITY_DELTA = "ACTIVITY_DELTA"
    # Reasoning (7) — replaces deprecated THINKING_*
    REASONING_START = "REASONING_START"
    REASONING_CONTENT = "REASONING_CONTENT"
    REASONING_END = "REASONING_END"
    REASONING_TOOL_CALL_START = "REASONING_TOOL_CALL_START"
    REASONING_TOOL_CALL_ARGS = "REASONING_TOOL_CALL_ARGS"
    REASONING_TOOL_CALL_END = "REASONING_TOOL_CALL_END"
    REASONING_TOOL_CALL_RESULT = "REASONING_TOOL_CALL_RESULT"
    # Special (2)
    RAW = "RAW"
    CUSTOM = "CUSTOM"

class AGUIEvent:
    """Single AG-UI event."""
    def __init__(self, type: AGUIEventType, data: dict = None, run_id: str = ""):
        self.type = type
        self.data = data or {}
        self.run_id = run_id
        self.timestamp = time.time()

    def to_sse(self) -> str:
        payload = {"type": self.type.value, "runId": self.run_id,
                   "timestamp": int(self.timestamp * 1000), **self.data}
        return f"event: {self.type.value}\ndata: {json.dumps(payload)}\n\n"

class AGUIServer:
    """Expose LARGESTACK agents via AG-UI protocol.

    Usage:
        from largestack._core.ag_ui import AGUIServer
        agui = AGUIServer(agent)
        app = agui.create_app()  # FastAPI app with /ag-ui/runs endpoint
    """
    def __init__(self, agent, agent_id: str = None):
        self.agent = agent
        self.agent_id = agent_id or agent.name

    async def run_stream(self, task: str, thread_id: str = None,
                         run_id: str = None) -> AsyncIterator[AGUIEvent]:
        """Execute agent and yield AG-UI events."""
        run_id = run_id or str(uuid.uuid4())
        thread_id = thread_id or str(uuid.uuid4())
        msg_id = str(uuid.uuid4())

        # RUN_STARTED
        yield AGUIEvent(AGUIEventType.RUN_STARTED, {
            "threadId": thread_id, "agentId": self.agent_id
        }, run_id)

        # STEP_STARTED
        yield AGUIEvent(AGUIEventType.STEP_STARTED, {
            "stepName": self.agent.name
        }, run_id)

        try:
            # TEXT_MESSAGE_START
            yield AGUIEvent(AGUIEventType.TEXT_MESSAGE_START, {
                "messageId": msg_id, "role": "assistant"
            }, run_id)

            # Stream tokens
            full_content = ""
            try:
                async for token in self.agent.stream(task):
                    full_content += token
                    yield AGUIEvent(AGUIEventType.TEXT_MESSAGE_CONTENT, {
                        "messageId": msg_id, "delta": token
                    }, run_id)
            except Exception:
                # Fallback to non-streaming
                result = await self.agent.run(task)
                full_content = result.content
                yield AGUIEvent(AGUIEventType.TEXT_MESSAGE_CONTENT, {
                    "messageId": msg_id, "delta": full_content
                }, run_id)

                # Emit tool calls if any
                if hasattr(result, 'tool_calls_made'):
                    for tc in result.tool_calls_made:
                        tc_id = str(uuid.uuid4())
                        yield AGUIEvent(AGUIEventType.TOOL_CALL_START, {
                            "toolCallId": tc_id, "toolName": tc
                        }, run_id)
                        yield AGUIEvent(AGUIEventType.TOOL_CALL_END, {
                            "toolCallId": tc_id
                        }, run_id)

                # STATE_SNAPSHOT with cost/trace info
                yield AGUIEvent(AGUIEventType.STATE_SNAPSHOT, {
                    "snapshot": {"cost": result.total_cost, "turns": result.turns,
                                 "trace_id": result.trace_id, "tools": result.tool_calls_made}
                }, run_id)

            # TEXT_MESSAGE_END
            yield AGUIEvent(AGUIEventType.TEXT_MESSAGE_END, {
                "messageId": msg_id
            }, run_id)

            # STEP_FINISHED
            yield AGUIEvent(AGUIEventType.STEP_FINISHED, {
                "stepName": self.agent.name
            }, run_id)

            # RUN_FINISHED
            yield AGUIEvent(AGUIEventType.RUN_FINISHED, {
                "threadId": thread_id
            }, run_id)

        except Exception as e:
            yield AGUIEvent(AGUIEventType.RUN_ERROR, {
                "message": str(e), "code": type(e).__name__
            }, run_id)

    def create_app(self):
        """Create FastAPI app with AG-UI /runs endpoint."""
        from fastapi import FastAPI
        from fastapi.responses import StreamingResponse

        app = FastAPI(title=f"Largestack AI — AG-UI — {self.agent_id}")

        @app.post("/ag-ui/runs")
        async def create_run(request: Request):
            body = await request.json()
            task = ""
            for msg in body.get("messages", []):
                if msg.get("role") == "user":
                    task = msg.get("content", "")
            thread_id = body.get("threadId")
            run_id = body.get("runId")

            async def generate():
                async for event in self.run_stream(task, thread_id, run_id):
                    yield event.to_sse()

            return StreamingResponse(generate(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        @app.get("/ag-ui/agent")
        async def agent_info():
            return {"id": self.agent_id, "name": self.agent.name,
                    "protocols": ["MCP", "A2A", "AG-UI"],
                    "capabilities": {"streaming": True, "tools": True, "state": True}}

        return app
