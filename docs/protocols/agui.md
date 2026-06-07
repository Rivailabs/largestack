# AG-UI — Agent-User Interaction Protocol

Status: **works** (offline-verified). `AGUIServer` is a public top-level import.

`AGUIServer` streams a Largestack `Agent` run to a frontend as
[AG-UI](https://docs.ag-ui.com) Server-Sent Events (SSE) — compatible with AG-UI
clients such as CopilotKit.

```python
from largestack import AGUIServer
```

| Piece | Import | Role |
|---|---|---|
| `AGUIServer` | `from largestack import AGUIServer` | Wraps an agent; streams events; builds a FastAPI app |
| `AGUIEvent` | `from largestack._core.ag_ui import AGUIEvent` | One event; `.to_sse()` renders the wire format |
| `AGUIEventType` | `from largestack._core.ag_ui import AGUIEventType` | Enum of all event types |

---

## Event types

The enum defines 26 event types. The ones emitted by `run_stream()` per run:

| Phase | Events emitted |
|---|---|
| Lifecycle | `RUN_STARTED`, `STEP_STARTED`, `STEP_FINISHED`, `RUN_FINISHED`, `RUN_ERROR` |
| Text | `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT` (per token/delta), `TEXT_MESSAGE_END` |
| State | `STATE_SNAPSHOT` (cost / turns / trace_id / tools, on the non-streaming path) |
| Tools | `TOOL_CALL_START`, `TOOL_CALL_END` (when the result reports tool calls) |

Other declared types (available on `AGUIEventType`, not all emitted by the default
flow): `STATE_DELTA`, `MESSAGES_SNAPSHOT`, `ACTIVITY_SNAPSHOT`/`ACTIVITY_DELTA`,
`REASONING_*` (7), `TOOL_CALL_ARGS`, `TOOL_CALL_RESULT`, `RAW`, `CUSTOM`.

Wire format of one SSE frame:

```text
event: TEXT_MESSAGE_CONTENT
data: {"type": "TEXT_MESSAGE_CONTENT", "runId": "...", "timestamp": 1780852927111, "messageId": "...", "delta": "Hello"}
```

---

## Minimal example

`run_stream()` is an async generator of `AGUIEvent`. Here it runs offline against a
`TestModel` via `agent.override(...)` — no API key, no network:

```python
import asyncio
from largestack import Agent, AGUIServer
from largestack.testing import TestModel

agent = Agent(name="assistant", llm="deepseek/deepseek-chat")
agui = AGUIServer(agent)

async def main():
    with agent.override(model=TestModel(custom_output_text="Hello from the agent!")):
        async for event in agui.run_stream("say hi"):
            print(event.type.value)            # RUN_STARTED, STEP_STARTED, TEXT_MESSAGE_START, ...
            if event.type.value == "TEXT_MESSAGE_CONTENT":
                print(event.to_sse())          # ready-to-write SSE frame

asyncio.run(main())
```

Emitted sequence: `RUN_STARTED → STEP_STARTED → TEXT_MESSAGE_START →
TEXT_MESSAGE_CONTENT → STATE_SNAPSHOT → TEXT_MESSAGE_END → STEP_FINISHED → RUN_FINISHED`.

---

## Serve over HTTP

`create_app()` returns a FastAPI app with the AG-UI endpoints:

```python
app = agui.create_app()
# uvicorn this_module:app
#   POST /ag-ui/runs   -> text/event-stream of AG-UI events
#   GET  /ag-ui/agent  -> agent id/name + capabilities
```

`POST /ag-ui/runs` accepts `{"messages": [...], "threadId": ..., "runId": ...}`; the
last `user` message becomes the task. The response is a `StreamingResponse` of SSE
frames (`Cache-Control: no-cache`, `X-Accel-Buffering: no`).

---

See also: [MCP](mcp.md) · [A2A](a2a.md)
