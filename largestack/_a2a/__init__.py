"""A2A (Agent2Agent) Protocol adapter (v0.12.0).

Closes the Google ADK / cross-framework interop gap. A2A v1.0 was
donated to the Linux Foundation and is in production at 150+ orgs
including SAP, ServiceNow, Salesforce, Workday.

A2A complements MCP:
- MCP — connects agents to **tools and data**
- A2A — connects agents to **other agents**

This module implements:

1. ``AgentCard`` — the discovery manifest. Lists what an agent can do.
2. ``A2AServer`` — exposes a LARGESTACK agent at an HTTP endpoint conforming
   to the A2A Task interface.
3. ``A2AClient`` — invokes a remote A2A agent via its AgentCard.
4. ``A2ATask`` — task lifecycle types (submitted → working → completed/failed).

Spec reference: https://a2a-protocol.org/

This is a **lightweight reference implementation** of the protocol.
For full v0.3+ features (gRPC, security card signing) production users
can install the official SDK and use LARGESTACK agents as task handlers.

Zero external deps for the core types + client. Server uses ``aiohttp``
if available; falls back to a stdlib-only test server.
"""

from __future__ import annotations
import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable, Literal

log = logging.getLogger("largestack.a2a")


# -------------------- Domain types --------------------

TaskState = Literal[
    "submitted",
    "working",
    "input-required",
    "completed",
    "failed",
    "canceled",
]


def _require_http_url(url: str) -> str:
    """Allow only absolute HTTP/HTTPS URLs before network requests."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be absolute and use http or https")
    return url


@dataclass
class AgentSkill:
    """A single capability advertised by an agent."""

    id: str
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)


@dataclass
class AgentCapabilities:
    """What protocol features the agent supports."""

    streaming: bool = False
    push_notifications: bool = False
    state_transition_history: bool = True


@dataclass
class AgentCard:
    """A2A agent discovery manifest. Served at ``/.well-known/agent.json``.

    Spec: https://a2a-protocol.org/latest/specification/agent-card/
    """

    name: str
    description: str
    url: str  # base URL where the agent is hosted
    version: str = "1.0.0"
    protocol_version: str = "0.3.0"
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)
    skills: list[AgentSkill] = field(default_factory=list)
    default_input_modes: list[str] = field(
        default_factory=lambda: ["text/plain"],
    )
    default_output_modes: list[str] = field(
        default_factory=lambda: ["text/plain"],
    )
    # Provider info (org publishing this agent)
    provider_name: str = ""
    provider_url: str = ""
    # Authentication required to invoke (none / api-key / oauth2)
    authentication: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgentCard":
        # Tolerant: drop unknown keys
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in d.items() if k in valid}

        # Re-hydrate nested types
        if "capabilities" in clean and isinstance(clean["capabilities"], dict):
            cap_valid = {f.name for f in AgentCapabilities.__dataclass_fields__.values()}
            clean["capabilities"] = AgentCapabilities(
                **{k: v for k, v in clean["capabilities"].items() if k in cap_valid}
            )
        if "skills" in clean and isinstance(clean["skills"], list):
            skill_valid = {f.name for f in AgentSkill.__dataclass_fields__.values()}
            clean["skills"] = [
                AgentSkill(**{k: v for k, v in s.items() if k in skill_valid})
                if isinstance(s, dict)
                else s
                for s in clean["skills"]
            ]
        return cls(**clean)


@dataclass
class A2AMessage:
    """A single message in a task conversation."""

    role: Literal["user", "agent"]
    parts: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=lambda: time.time())

    @classmethod
    def text(cls, role: Literal["user", "agent"], text: str) -> "A2AMessage":
        return cls(role=role, parts=[{"type": "text", "text": text}])

    def get_text(self) -> str:
        """Concatenate all text parts."""
        return "\n".join(p.get("text", "") for p in self.parts if p.get("type") == "text")


@dataclass
class A2ATask:
    """A2A task lifecycle object."""

    id: str
    state: TaskState = "submitted"
    messages: list[A2AMessage] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, msg: A2AMessage) -> None:
        self.messages.append(msg)
        self.updated_at = time.time()

    def add_artifact(self, artifact: dict[str, Any]) -> None:
        self.artifacts.append(artifact)
        self.updated_at = time.time()

    def transition(self, state: TaskState, error: str = "") -> None:
        self.state = state
        self.updated_at = time.time()
        if error:
            self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "messages": [
                {
                    "role": m.role,
                    "parts": m.parts,
                    "timestamp": m.timestamp,
                }
                for m in self.messages
            ],
            "artifacts": self.artifacts,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "metadata": self.metadata,
        }


# -------------------- Server --------------------

# Type signature for the agent handler callable that the server wraps
AgentHandler = Callable[[str, A2ATask], Awaitable[str]]


class A2AServer:
    """Exposes a LARGESTACK agent as an A2A-compliant HTTP endpoint.

    Provides:
    - ``GET /.well-known/agent.json`` → AgentCard
    - ``POST /tasks/send`` → submit a new task (sync)
    - ``GET /tasks/{id}`` → query task status
    - ``POST /tasks/{id}/cancel`` → cancel a task

    Args:
        card: the ``AgentCard`` describing this agent
        handler: async function ``(input_text, task) -> output_text``
        task_ttl_seconds: how long completed tasks are retained (default 1hr)
    """

    def __init__(
        self,
        *,
        card: AgentCard,
        handler: AgentHandler,
        task_ttl_seconds: float = 3600.0,
    ):
        self.card = card
        self.handler = handler
        self.task_ttl_seconds = task_ttl_seconds
        self._tasks: dict[str, A2ATask] = {}
        self._lock = asyncio.Lock()

    async def submit_task(
        self,
        input_text: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> A2ATask:
        """Submit a new task. Returns the completed (or failed) task."""
        task = A2ATask(
            id=task_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )
        task.add_message(A2AMessage.text("user", input_text))

        async with self._lock:
            self._tasks[task.id] = task

        task.transition("working")
        try:
            output = await self.handler(input_text, task)
            task.add_message(A2AMessage.text("agent", str(output)))
            task.transition("completed")
        except asyncio.CancelledError:
            task.transition("canceled")
            raise
        except Exception as e:
            task.transition("failed", error=str(e))
            log.exception(f"task {task.id} failed")

        return task

    async def get_task(self, task_id: str) -> A2ATask | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.state in ("completed", "failed", "canceled"):
                return False
            task.transition("canceled")
            return True

    async def purge_expired_tasks(self) -> int:
        """Remove tasks older than ``task_ttl_seconds``."""
        async with self._lock:
            now = time.time()
            to_delete = [
                tid
                for tid, t in self._tasks.items()
                if t.state in ("completed", "failed", "canceled")
                and (now - t.updated_at) > self.task_ttl_seconds
            ]
            for tid in to_delete:
                del self._tasks[tid]
            return len(to_delete)

    # -------------------- HTTP request handlers --------------------

    async def handle_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Generic request dispatcher. Returns (status_code, body_dict).

        Implementers can wire this into aiohttp / FastAPI / starlette.
        """
        # Discovery
        if method == "GET" and path == "/.well-known/agent.json":
            return 200, self.card.to_dict()

        # Submit task
        if method == "POST" and path == "/tasks/send":
            body = body or {}
            input_text = body.get("input", "")
            if not input_text:
                # Fall back to first user message text
                msg = body.get("message", {})
                if isinstance(msg, dict):
                    parts = msg.get("parts", [])
                    input_text = "\n".join(
                        p.get("text", "")
                        for p in parts
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
            if not input_text:
                return 400, {"error": "input is required"}
            task = await self.submit_task(
                input_text,
                task_id=body.get("id"),
                metadata=body.get("metadata") or {},
            )
            return 200, task.to_dict()

        # Query task
        if method == "GET" and path.startswith("/tasks/"):
            task_id = path[len("/tasks/") :].split("/")[0]
            task = await self.get_task(task_id)
            if not task:
                return 404, {"error": f"task {task_id} not found"}
            return 200, task.to_dict()

        # Cancel task
        if method == "POST" and path.startswith("/tasks/") and path.endswith("/cancel"):
            task_id = path[len("/tasks/") : -len("/cancel")]
            ok = await self.cancel_task(task_id)
            if not ok:
                return 400, {"error": "cannot cancel task"}
            return 200, {"id": task_id, "state": "canceled"}

        return 404, {"error": "unknown endpoint"}


# -------------------- Client --------------------


class A2AClient:
    """Client for invoking a remote A2A agent.

    Uses ``aiohttp`` if available, falls back to ``urllib`` (sync).

    Args:
        base_url: base URL of the remote agent (e.g. ``https://agent.example.com``)
        api_key: optional bearer token
        timeout: per-request timeout in seconds
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _post_json(
        self,
        path: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        url = self.base_url + path
        try:
            import aiohttp
        except ImportError:
            return await self._post_json_urllib(url, body)

        async with aiohttp.ClientSession(headers=self._headers) as s:
            async with s.post(
                url,
                json=body,
                timeout=aiohttp.ClientTimeout(
                    total=self.timeout,
                ),
            ) as resp:
                return resp.status, await resp.json()

    async def _get_json(
        self,
        path: str,
    ) -> tuple[int, dict[str, Any]]:
        url = self.base_url + path
        try:
            import aiohttp
        except ImportError:
            return await self._get_json_urllib(url)

        async with aiohttp.ClientSession(headers=self._headers) as s:
            async with s.get(
                url,
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                return resp.status, await resp.json()

    async def _post_json_urllib(
        self,
        url: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """stdlib fallback. Synchronous, run in thread."""
        import urllib.error
        import urllib.request

        def _do():
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers=self._headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # nosec B310
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read().decode())
                except Exception:
                    return e.code, {"error": str(e)}

        return await asyncio.to_thread(_do)

    async def _get_json_urllib(
        self,
        url: str,
    ) -> tuple[int, dict[str, Any]]:
        import urllib.error
        import urllib.request

        def _do():
            req = urllib.request.Request(
                url,
                headers=self._headers,
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # nosec B310
                    return r.status, json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    return e.code, json.loads(e.read().decode())
                except Exception:
                    return e.code, {"error": str(e)}

        return await asyncio.to_thread(_do)

    # -------------------- Public API --------------------

    async def discover(self) -> AgentCard:
        """Fetch the agent's AgentCard."""
        status, body = await self._get_json("/.well-known/agent.json")
        if status != 200:
            raise RuntimeError(f"discover failed: HTTP {status} - {body.get('error', '')}")
        return AgentCard.from_dict(body)

    async def send_task(
        self,
        input_text: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> A2ATask:
        """Submit a task and wait for completion."""
        body: dict[str, Any] = {"input": input_text}
        if task_id:
            body["id"] = task_id
        if metadata:
            body["metadata"] = metadata
        status, resp = await self._post_json("/tasks/send", body)
        if status != 200:
            raise RuntimeError(f"send_task failed: HTTP {status} - {resp.get('error', '')}")
        return _task_from_dict(resp)

    async def get_task(self, task_id: str) -> A2ATask | None:
        status, resp = await self._get_json(f"/tasks/{task_id}")
        if status == 404:
            return None
        if status != 200:
            raise RuntimeError(f"get_task failed: HTTP {status} - {resp.get('error', '')}")
        return _task_from_dict(resp)

    async def cancel_task(self, task_id: str) -> bool:
        status, _ = await self._post_json(f"/tasks/{task_id}/cancel", {})
        return status == 200


def _task_from_dict(d: dict[str, Any]) -> A2ATask:
    """Hydrate an A2ATask from its serialized form."""
    msgs = []
    for m in d.get("messages", []):
        if isinstance(m, dict):
            msgs.append(
                A2AMessage(
                    role=m.get("role", "user"),
                    parts=m.get("parts", []),
                    timestamp=m.get("timestamp", time.time()),
                )
            )
    return A2ATask(
        id=d.get("id", ""),
        state=d.get("state", "submitted"),
        messages=msgs,
        artifacts=d.get("artifacts", []),
        created_at=d.get("created_at", time.time()),
        updated_at=d.get("updated_at", time.time()),
        error=d.get("error", ""),
        metadata=d.get("metadata", {}),
    )


# -------------------- LARGESTACK-side helpers --------------------


def expose_largestack_agent(
    largestack_agent,
    *,
    name: str,
    description: str,
    url: str,
    skills: list[AgentSkill] | None = None,
    provider_name: str = "RivaiLabs",
    provider_url: str = "https://largestack.ai",
) -> A2AServer:
    """Convenience: wrap a LARGESTACK Agent as an A2A server.

    The agent must have an async ``.run(input)`` method that returns an
    object with a ``.content`` attribute (LARGESTACK Agent contract).
    """
    card = AgentCard(
        name=name,
        description=description,
        url=url,
        skills=skills or [],
        provider_name=provider_name,
        provider_url=provider_url,
    )

    async def handler(input_text: str, task: A2ATask) -> str:
        resp = await largestack_agent.run(input_text)
        return getattr(resp, "content", str(resp))

    return A2AServer(card=card, handler=handler)
