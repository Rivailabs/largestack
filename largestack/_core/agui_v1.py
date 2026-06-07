"""AG-UI (Agent-User Interaction) Protocol — 25 event types.

Spec: https://docs.ag-ui.com/concepts/events

Event categories:
  - Lifecycle: RUN_STARTED, RUN_FINISHED, RUN_ERROR, STEP_STARTED, STEP_FINISHED
  - Text: TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT, TEXT_MESSAGE_END, TEXT_MESSAGE_CHUNK
  - Tools: TOOL_CALL_START, TOOL_CALL_ARGS, TOOL_CALL_END, TOOL_CALL_CHUNK, TOOL_CALL_RESULT
  - State: STATE_SNAPSHOT, STATE_DELTA, MESSAGES_SNAPSHOT
  - Reasoning: REASONING_START, REASONING_CONTENT, REASONING_END, REASONING_CHUNK
  - Custom: CUSTOM, RAW
"""

from __future__ import annotations
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, AsyncIterator

log = logging.getLogger("largestack.agui")


class EventType(str, Enum):
    """AG-UI event types (25 total)."""

    # Lifecycle (5)
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    STEP_STARTED = "STEP_STARTED"
    STEP_FINISHED = "STEP_FINISHED"

    # Text messages (4)
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TEXT_MESSAGE_CHUNK = "TEXT_MESSAGE_CHUNK"

    # Tool calls (5)
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_CHUNK = "TOOL_CALL_CHUNK"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    # State management (3)
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    MESSAGES_SNAPSHOT = "MESSAGES_SNAPSHOT"

    # Reasoning (4)
    REASONING_START = "REASONING_START"
    REASONING_CONTENT = "REASONING_CONTENT"
    REASONING_END = "REASONING_END"
    REASONING_CHUNK = "REASONING_CHUNK"

    # Other (4)
    CUSTOM = "CUSTOM"
    RAW = "RAW"
    THINKING_START = "THINKING_START"  # Deprecated alias for REASONING_START
    THINKING_END = "THINKING_END"  # Deprecated alias for REASONING_END


@dataclass
class AGUIEvent:
    """Base AG-UI event."""

    type: EventType
    timestamp: float = field(default_factory=time.time)
    raw_event: dict | None = None

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        data = {"type": self.type.value, "timestamp": self.timestamp}
        for k, v in self.__dict__.items():
            if k not in ("type", "timestamp", "raw_event") and v is not None:
                data[k] = v.value if isinstance(v, Enum) else v
        return f"data: {json.dumps(data)}\n\n"


@dataclass
class RunStarted(AGUIEvent):
    type: EventType = EventType.RUN_STARTED
    thread_id: str = ""
    run_id: str = ""


@dataclass
class RunFinished(AGUIEvent):
    type: EventType = EventType.RUN_FINISHED
    thread_id: str = ""
    run_id: str = ""
    result: Any = None


@dataclass
class RunError(AGUIEvent):
    type: EventType = EventType.RUN_ERROR
    thread_id: str = ""
    run_id: str = ""
    message: str = ""
    code: str | None = None


@dataclass
class TextMessageStart(AGUIEvent):
    type: EventType = EventType.TEXT_MESSAGE_START
    message_id: str = ""
    role: str = "assistant"


@dataclass
class TextMessageContent(AGUIEvent):
    type: EventType = EventType.TEXT_MESSAGE_CONTENT
    message_id: str = ""
    delta: str = ""


@dataclass
class TextMessageEnd(AGUIEvent):
    type: EventType = EventType.TEXT_MESSAGE_END
    message_id: str = ""


@dataclass
class ToolCallStart(AGUIEvent):
    type: EventType = EventType.TOOL_CALL_START
    tool_call_id: str = ""
    tool_call_name: str = ""
    parent_message_id: str = ""


@dataclass
class ToolCallArgs(AGUIEvent):
    type: EventType = EventType.TOOL_CALL_ARGS
    tool_call_id: str = ""
    delta: str = ""


@dataclass
class ToolCallEnd(AGUIEvent):
    type: EventType = EventType.TOOL_CALL_END
    tool_call_id: str = ""


@dataclass
class ToolCallResult(AGUIEvent):
    type: EventType = EventType.TOOL_CALL_RESULT
    tool_call_id: str = ""
    content: str = ""
    role: str = "tool"


@dataclass
class StateSnapshot(AGUIEvent):
    type: EventType = EventType.STATE_SNAPSHOT
    snapshot: dict = field(default_factory=dict)


@dataclass
class StateDelta(AGUIEvent):
    """JSON Patch (RFC 6902) format."""

    type: EventType = EventType.STATE_DELTA
    delta: list = field(default_factory=list)


@dataclass
class ReasoningStart(AGUIEvent):
    type: EventType = EventType.REASONING_START
    message_id: str = ""


@dataclass
class ReasoningContent(AGUIEvent):
    type: EventType = EventType.REASONING_CONTENT
    message_id: str = ""
    delta: str = ""


@dataclass
class ReasoningEnd(AGUIEvent):
    type: EventType = EventType.REASONING_END
    message_id: str = ""


class AGUIEmitter:
    """Emit AG-UI events as Server-Sent Event stream.

    Example:
        emitter = AGUIEmitter()
        async for event in emitter.run_with_agent(agent, "Hello"):
            yield event.to_sse()
    """

    def __init__(self, thread_id: str | None = None, run_id: str | None = None):
        self.thread_id = thread_id or str(uuid.uuid4())
        self.run_id = run_id or str(uuid.uuid4())
        self.events_emitted = 0

    def run_started(self) -> RunStarted:
        self.events_emitted += 1
        return RunStarted(thread_id=self.thread_id, run_id=self.run_id)

    def run_finished(self, result: Any = None) -> RunFinished:
        self.events_emitted += 1
        return RunFinished(thread_id=self.thread_id, run_id=self.run_id, result=result)

    def run_error(self, message: str, code: str | None = None) -> RunError:
        self.events_emitted += 1
        return RunError(thread_id=self.thread_id, run_id=self.run_id, message=message, code=code)

    def text_message(self, content: str, message_id: str | None = None) -> list[AGUIEvent]:
        """Stream a text message as start/content/end events."""
        mid = message_id or str(uuid.uuid4())
        self.events_emitted += 3
        return [
            TextMessageStart(message_id=mid),
            TextMessageContent(message_id=mid, delta=content),
            TextMessageEnd(message_id=mid),
        ]

    def tool_call(self, tool_call_id: str, name: str, args: dict, result: Any) -> list[AGUIEvent]:
        """Emit tool call lifecycle events."""
        self.events_emitted += 4
        return [
            ToolCallStart(tool_call_id=tool_call_id, tool_call_name=name),
            ToolCallArgs(tool_call_id=tool_call_id, delta=json.dumps(args)),
            ToolCallEnd(tool_call_id=tool_call_id),
            ToolCallResult(tool_call_id=tool_call_id, content=json.dumps(result)),
        ]

    def state_snapshot(self, state: dict) -> StateSnapshot:
        self.events_emitted += 1
        return StateSnapshot(snapshot=state)

    def state_delta(self, patches: list[dict]) -> StateDelta:
        """Emit JSON Patch (RFC 6902) state delta."""
        self.events_emitted += 1
        return StateDelta(delta=patches)

    def reasoning(self, content: str) -> list[AGUIEvent]:
        mid = str(uuid.uuid4())
        self.events_emitted += 3
        return [
            ReasoningStart(message_id=mid),
            ReasoningContent(message_id=mid, delta=content),
            ReasoningEnd(message_id=mid),
        ]

    @property
    def stats(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "run_id": self.run_id,
            "events_emitted": self.events_emitted,
            "supported_event_types": len(EventType),
        }


def create_fastapi_app(emitter_factory):
    """Mount AG-UI server with FastAPI.

    Args:
        emitter_factory: async generator yielding AGUIEvent instances
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import StreamingResponse

    app = FastAPI(title="AG-UI Server")

    @app.post("/agui/run")
    async def run(request: Request):
        body = await request.json()
        prompt = body.get("prompt", "")

        async def event_stream():
            async for event in emitter_factory(prompt):
                yield event.to_sse()

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/agui/info")
    def info():
        return {
            "protocol": "ag-ui",
            "supported_event_types": [e.value for e in EventType],
            "event_count": len(EventType),
        }

    return app
