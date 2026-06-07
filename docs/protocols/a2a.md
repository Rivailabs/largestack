# A2A — Agent-to-Agent Protocol v1.0

Status: **partial / reference**. The A2A v1.0 server is a reference implementation
(JSON-RPC 2.0 + Agent Card + task lifecycle). It is **not** exported from the
top-level `largestack` package — import it from `largestack._core.a2a_v1`.

Spec: <https://a2a-protocol.org/latest/specification/>

```python
from largestack._core.a2a_v1 import A2AServer, AgentCard, Task, TaskState
```

| Piece | What it is |
|---|---|
| `AgentCard` | Served at `/.well-known/agent-card.json`; optional JWS signature |
| `A2AServer` | JSON-RPC 2.0 server with task lifecycle + skills |
| `Task` / `TaskState` | A task and its `SCREAMING_SNAKE_CASE` v1.0 states |
| `create_fastapi_app(server)` | Mounts the card + `/a2a` endpoint on a FastAPI app |

Task states (`TaskState`): `SUBMITTED`, `WORKING`, `INPUT_REQUIRED`, `COMPLETED`, `FAILED`, `CANCELED`.

JSON-RPC methods handled: `message/send`, `tasks/get`, `tasks/cancel`.

---

## Construct a server + handler

A handler is `async def(task: Task) -> Task`. Set the terminal state (or leave it
`WORKING` and the server marks it `COMPLETED`).

```python
import asyncio
from largestack._core.a2a_v1 import A2AServer, Task, TaskState

server = A2AServer(
    name="echo-agent",
    description="Echoes the user message",
    version="1.0.0",
    url="http://localhost:8000/a2a",
)
server.add_skill("echo", "Echo", "Echo text back", tags=["demo"])

async def handle(task: Task) -> Task:
    user_text = task.messages[-1].get("parts", [{}])[0].get("text", "")
    task.artifacts.append({"parts": [{"type": "text", "text": f"echo: {user_text}"}]})
    task.transition(TaskState.COMPLETED)
    return task

server.register_handler(handle)

async def main():
    req = {
        "jsonrpc": "2.0", "id": 1, "method": "message/send",
        "params": {"message": {"role": "user", "parts": [{"type": "text", "text": "hi"}]}},
    }
    resp = await server.handle_request(req)
    print(resp["result"]["status"]["state"])   # COMPLETED
    print(resp["result"]["artifacts"])           # [{'parts': [{'type': 'text', 'text': 'echo: hi'}]}]

asyncio.run(main())
```

---

## Agent Card

`get_agent_card()` returns the dict served at `/.well-known/agent-card.json`:

```python
import json
print(json.dumps(server.get_agent_card(), indent=2))
```

```json
{
  "name": "echo-agent",
  "description": "Echoes the user message",
  "version": "1.0.0",
  "url": "http://localhost:8000/a2a",
  "capabilities": {"streaming": true, "pushNotifications": false},
  "authentication": {"schemes": ["none"]},
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [{"id": "echo", "name": "Echo", "description": "Echo text back", "tags": ["demo"]}]
}
```

### Signing (reference)

Pass `signing_key=` to attach a signature to the card. **Note:** the current
implementation uses an HMAC-SHA256 digest (placed in a `_signature` field), not a
full RFC 7515 JWS — treat it as a reference/interop seam, not a production trust anchor.

```python
from largestack._core.a2a_v1 import AgentCard

card = AgentCard(name="x", description="y", version="1.0.0", url="http://h/a2a")
signed = card.sign_jws(b"secret-key-bytes")
print("_signature" in signed)   # True
```

---

## Serve over HTTP

```python
from largestack._core.a2a_v1 import create_fastapi_app

app = create_fastapi_app(server)
# uvicorn this_module:app  ->  GET /.well-known/agent-card.json, POST /a2a, GET /a2a/info
```

Inspect runtime counters with `server.stats` (task totals by state, skill count,
protocol version).

---

See also: [MCP](mcp.md) · [AG-UI](agui.md)
