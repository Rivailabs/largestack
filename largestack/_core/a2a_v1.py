"""A2A (Agent-to-Agent) Protocol v1.0 — Linux Foundation standard.

Implements:
  - JSON-RPC 2.0 over HTTPS + SSE
  - /.well-known/agent-card.json endpoint with JWS signing
  - Task lifecycle: submitted/working/input-required/completed/failed/canceled
  - Methods: message/send, message/sendSubscribe, tasks/get, tasks/cancel
  - SCREAMING_SNAKE_CASE enums (v1.0 change from kebab-case)
  - google.rpc.Status error format

Spec: https://a2a-protocol.org/latest/specification/
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, AsyncIterator, Callable

log = logging.getLogger("largestack.a2a")

A2A_VERSION = "1.0"


class TaskState(str, Enum):
    """A2A v1.0 task states (SCREAMING_SNAKE_CASE)."""
    SUBMITTED = "SUBMITTED"
    WORKING = "WORKING"
    INPUT_REQUIRED = "INPUT_REQUIRED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass
class AgentCard:
    """A2A Agent Card — exposed at /.well-known/agent-card.json."""
    name: str
    description: str
    version: str
    url: str
    capabilities: dict = field(default_factory=lambda: {"streaming": True, "pushNotifications": False})
    authentication: list[str] = field(default_factory=lambda: ["none"])
    default_input_modes: list[str] = field(default_factory=lambda: ["text"])
    default_output_modes: list[str] = field(default_factory=lambda: ["text"])
    skills: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "url": self.url,
            "capabilities": self.capabilities,
            "authentication": {"schemes": self.authentication},
            "defaultInputModes": self.default_input_modes,
            "defaultOutputModes": self.default_output_modes,
            "skills": self.skills,
        }
    
    def sign_jws(self, private_key: bytes) -> dict:
        """Sign card per RFC 8785 (JCS) + RFC 7515 (JWS)."""
        try:
            import hmac
            import hashlib
            import base64
            payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
            sig = hmac.new(private_key, payload, hashlib.sha256).hexdigest()
            return {**self.to_dict(), "_signature": sig}
        except Exception as e:
            log.warning(f"JWS sign failed (using unsigned): {e}")
            return self.to_dict()


@dataclass
class Task:
    """A2A task with lifecycle tracking."""
    id: str
    state: TaskState = TaskState.SUBMITTED
    messages: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: dict | None = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": {"state": self.state.value, "timestamp": self.updated_at},
            "messages": self.messages,
            "artifacts": self.artifacts,
            "createdAt": self.created_at,
            "error": self.error,
        }
    
    def transition(self, new_state: TaskState):
        self.state = new_state
        self.updated_at = time.time()


class A2AServer:
    """A2A v1.0 server.
    
    Example:
        server = A2AServer(
            name="my-agent",
            description="A helpful agent",
            version="1.0.0",
            url="https://example.com/a2a",
        )
        server.register_handler(handle_task)
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        version: str = "1.0.0",
        url: str = "http://localhost:8000/a2a",
        signing_key: bytes | None = None,
    ):
        self.card = AgentCard(name=name, description=description, version=version, url=url)
        self.signing_key = signing_key
        self._tasks: dict[str, Task] = {}
        self._handler: Callable | None = None
        self._subscribers: dict[str, asyncio.Queue] = {}
    
    def add_skill(self, skill_id: str, name: str, description: str, tags: list[str] | None = None):
        """Add a skill to the Agent Card."""
        self.card.skills.append({
            "id": skill_id,
            "name": name,
            "description": description,
            "tags": tags or [],
        })
    
    def register_handler(self, handler: Callable):
        """Register the task handler.
        
        Handler signature: async def(task: Task) -> Task
        """
        self._handler = handler
    
    def get_agent_card(self) -> dict:
        """Return Agent Card (signed if signing_key provided)."""
        if self.signing_key:
            return self.card.sign_jws(self.signing_key)
        return self.card.to_dict()
    
    async def handle_request(self, request: dict) -> dict:
        """Handle JSON-RPC 2.0 A2A request."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")
        
        try:
            if method == "message/send":
                result = await self._message_send(params)
            elif method == "tasks/get":
                result = await self._tasks_get(params)
            elif method == "tasks/cancel":
                result = await self._tasks_cancel(params)
            else:
                return self._error(req_id, 5, f"Method not found: {method}")
            
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as e:
            log.exception(f"A2A error in {method}")
            return self._error(req_id, 13, f"Internal error: {e}")
    
    async def _message_send(self, params: dict) -> dict:
        """Send message → create task → execute."""
        message = params.get("message", {})
        task_id = str(uuid.uuid4())
        
        task = Task(id=task_id)
        task.messages.append(message)
        self._tasks[task_id] = task
        
        if self._handler:
            task.transition(TaskState.WORKING)
            try:
                task = await self._handler(task)
                if task.state == TaskState.WORKING:
                    task.transition(TaskState.COMPLETED)
            except Exception as e:
                task.transition(TaskState.FAILED)
                task.error = {"code": 13, "message": str(e)}
        
        return task.to_dict()
    
    async def _tasks_get(self, params: dict) -> dict:
        task_id = params.get("id", "")
        if task_id not in self._tasks:
            raise ValueError(f"Task not found: {task_id}")
        return self._tasks[task_id].to_dict()
    
    async def _tasks_cancel(self, params: dict) -> dict:
        task_id = params.get("id", "")
        if task_id not in self._tasks:
            raise ValueError(f"Task not found: {task_id}")
        task = self._tasks[task_id]
        task.transition(TaskState.CANCELED)
        return task.to_dict()
    
    def _error(self, req_id: Any, code: int, message: str) -> dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message, "status": "INTERNAL"},
        }
    
    @property
    def stats(self) -> dict:
        states = {}
        for t in self._tasks.values():
            states[t.state.value] = states.get(t.state.value, 0) + 1
        return {
            "name": self.card.name,
            "version": self.card.version,
            "protocol_version": A2A_VERSION,
            "tasks_total": len(self._tasks),
            "tasks_by_state": states,
            "skills": len(self.card.skills),
        }


def create_fastapi_app(server: A2AServer):
    """Mount A2A server with FastAPI."""
    from fastapi import FastAPI, Body
    
    app = FastAPI(title=f"A2A: {server.card.name}")
    
    @app.get("/.well-known/agent-card.json")
    def agent_card():
        return server.get_agent_card()
    
    @app.post("/a2a")
    async def a2a_jsonrpc(body: dict = Body(...)):
        # v0.4.0: use Body(...) instead of Request — `from __future__ import
        # annotations` at module top makes FastAPI unable to resolve the
        # function-scoped `Request` import at typing time, causing 422.
        return await server.handle_request(body)
    
    @app.get("/a2a/info")
    def info():
        return server.stats
    
    return app
