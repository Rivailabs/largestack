"""A2A v0.3 streaming + signed AgentCards (v0.13.0).

Extends ``largestack._a2a`` with two A2A v0.3-spec features:

1. **SSE streaming** — long-running tasks emit progress via
   server-sent events (``text/event-stream``)
2. **Signed AgentCards** — cards can be JWT-signed for trust /
   anti-spoofing

Both features are optional. The stdlib-only client + server still work
without them.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from largestack._a2a import A2ATask, A2AMessage, AgentCard, A2AServer

log = logging.getLogger("largestack.a2a.v03")


# -------------------- SSE streaming --------------------

@dataclass
class TaskStreamEvent:
    """One event in an A2A SSE stream."""
    event: str  # 'state_change', 'message', 'artifact', 'done', 'error'
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: time.time())

    def to_sse(self) -> str:
        """Encode as a single SSE message (with trailing blank line)."""
        return (
            f"event: {self.event}\n"
            f"data: {json.dumps(self.data)}\n\n"
        )


class StreamingA2AServer(A2AServer):
    """A2A server with SSE streaming support.

    Adds:
    - ``stream_task(input_text)`` — async generator yielding
      ``TaskStreamEvent`` objects
    - HTTP endpoint ``POST /tasks/sendSubscribe`` (streaming variant)

    The handler can be either:
    - The standard ``handler(input_text, task) -> str`` (auto-stream
      state transitions)
    - A streaming-aware ``handler(input_text, task, emit) -> str`` where
      ``emit`` is an async callable for pushing intermediate events
    """

    def __init__(
        self,
        *,
        card: AgentCard,
        handler: Callable[..., Awaitable[str]],
        task_ttl_seconds: float = 3600.0,
    ):
        super().__init__(
            card=card, handler=handler, task_ttl_seconds=task_ttl_seconds,
        )

    async def stream_task(
        self,
        input_text: str,
        *,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[TaskStreamEvent]:
        """Submit a task and yield events as it progresses."""
        import uuid
        task = A2ATask(
            id=task_id or str(uuid.uuid4()),
            metadata=metadata or {},
        )
        task.add_message(A2AMessage.text("user", input_text))

        async with self._lock:
            self._tasks[task.id] = task

        # Submitted
        yield TaskStreamEvent(
            event="state_change",
            data={"task_id": task.id, "state": "submitted"},
        )

        # Working
        task.transition("working")
        yield TaskStreamEvent(
            event="state_change",
            data={"task_id": task.id, "state": "working"},
        )

        # Build emit callback for streaming-aware handlers
        events_queue: asyncio.Queue[TaskStreamEvent | None] = asyncio.Queue()

        async def emit(event_type: str, data: dict[str, Any]) -> None:
            await events_queue.put(TaskStreamEvent(
                event=event_type, data={**data, "task_id": task.id},
            ))

        # Run the handler in a separate task so we can drain the queue
        async def run_handler():
            try:
                # Detect signature
                import inspect
                sig = inspect.signature(self.handler)
                if len(sig.parameters) >= 3:
                    out = await self.handler(input_text, task, emit)
                else:
                    out = await self.handler(input_text, task)
                task.add_message(A2AMessage.text("agent", str(out)))
                task.transition("completed")
                await events_queue.put(TaskStreamEvent(
                    event="message",
                    data={"task_id": task.id, "role": "agent",
                          "text": str(out)},
                ))
                await events_queue.put(TaskStreamEvent(
                    event="state_change",
                    data={"task_id": task.id, "state": "completed"},
                ))
            except Exception as e:
                task.transition("failed", error=str(e))
                await events_queue.put(TaskStreamEvent(
                    event="error",
                    data={"task_id": task.id, "error": str(e)},
                ))
                await events_queue.put(TaskStreamEvent(
                    event="state_change",
                    data={"task_id": task.id, "state": "failed"},
                ))
            finally:
                await events_queue.put(None)  # sentinel

        handler_task = asyncio.create_task(run_handler())
        try:
            while True:
                ev = await events_queue.get()
                if ev is None:
                    break
                yield ev
        finally:
            if not handler_task.done():
                handler_task.cancel()
                try:
                    await handler_task
                except (asyncio.CancelledError, Exception):
                    pass

        # Final 'done' marker
        yield TaskStreamEvent(
            event="done",
            data={"task_id": task.id, "final_state": task.state},
        )

    async def handle_streaming_request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """SSE-yielding variant for ``POST /tasks/sendSubscribe``.

        Yields raw SSE-formatted strings ready for ``text/event-stream``.
        """
        if method != "POST" or path != "/tasks/sendSubscribe":
            yield TaskStreamEvent(
                event="error", data={"error": "unknown endpoint"},
            ).to_sse()
            return

        body = body or {}
        input_text = body.get("input", "")
        if not input_text:
            msg = body.get("message", {})
            if isinstance(msg, dict):
                parts = msg.get("parts", [])
                input_text = "\n".join(
                    p.get("text", "") for p in parts
                    if isinstance(p, dict) and p.get("type") == "text"
                )
        if not input_text:
            yield TaskStreamEvent(
                event="error", data={"error": "input is required"},
            ).to_sse()
            return

        async for ev in self.stream_task(
            input_text,
            task_id=body.get("id"),
            metadata=body.get("metadata") or {},
        ):
            yield ev.to_sse()


# -------------------- Signed AgentCards --------------------

@dataclass
class SignedAgentCard:
    """An ``AgentCard`` plus a signature.

    Format::

        {
          "card": {...AgentCard...},
          "signature": {
            "alg": "HS256" | "RS256",
            "kid": "key-id",
            "value": "<base64-encoded>",
            "issued_at": 1234567890.0,
            "expires_at": 1234567890.0,
          }
        }
    """
    card: AgentCard
    signature: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "card": self.card.to_dict(),
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SignedAgentCard":
        return cls(
            card=AgentCard.from_dict(d.get("card", {})),
            signature=d.get("signature", {}),
        )


def sign_agent_card_hs256(
    card: AgentCard,
    *,
    secret: str,
    kid: str = "default",
    ttl_seconds: float = 86400.0,
) -> SignedAgentCard:
    """Sign an ``AgentCard`` with HMAC-SHA256.

    Used for trusted-internal interop where both parties share a secret.
    For cross-org interop use ``sign_agent_card_rs256`` (asymmetric).
    """
    if not secret:
        raise ValueError("secret is required")
    now = time.time()
    payload = {
        "card": card.to_dict(),
        "issued_at": now,
        "expires_at": now + ttl_seconds,
        "kid": kid,
    }
    payload_bytes = _canonical_json(payload).encode()
    sig = hmac.new(
        secret.encode(), payload_bytes, hashlib.sha256,
    ).digest()
    return SignedAgentCard(
        card=card,
        signature={
            "alg": "HS256",
            "kid": kid,
            "value": _b64url(sig),
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        },
    )


def verify_agent_card_hs256(
    signed: SignedAgentCard,
    *,
    secret: str,
) -> tuple[bool, str]:
    """Verify a HS256-signed ``SignedAgentCard``.

    Returns ``(ok, reason_or_empty)``. ``ok=False`` indicates either
    signature mismatch, expired, or malformed.
    """
    sig = signed.signature
    if not sig:
        return False, "no signature"
    if sig.get("alg") != "HS256":
        return False, f"unsupported alg: {sig.get('alg')}"
    issued = sig.get("issued_at")
    expires = sig.get("expires_at")
    if expires is None or expires < time.time():
        return False, "signature expired"

    payload = {
        "card": signed.card.to_dict(),
        "issued_at": issued,
        "expires_at": expires,
        "kid": sig.get("kid", "default"),
    }
    expected = hmac.new(
        secret.encode(),
        _canonical_json(payload).encode(),
        hashlib.sha256,
    ).digest()
    expected_b64 = _b64url(expected)
    if not hmac.compare_digest(expected_b64, sig.get("value", "")):
        return False, "signature mismatch"
    return True, ""


def sign_agent_card_rs256(
    card: AgentCard,
    *,
    private_key_pem: bytes | str,
    kid: str = "default",
    ttl_seconds: float = 86400.0,
) -> SignedAgentCard:
    """Sign an ``AgentCard`` with RS256 (asymmetric).

    Requires the ``cryptography`` package.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as e:
        raise ImportError(
            "cryptography required for RS256. "
            "Install with: pip install cryptography"
        ) from e

    if isinstance(private_key_pem, str):
        private_key_pem = private_key_pem.encode()
    private_key = serialization.load_pem_private_key(
        private_key_pem, password=None,
    )

    now = time.time()
    payload = {
        "card": card.to_dict(),
        "issued_at": now,
        "expires_at": now + ttl_seconds,
        "kid": kid,
    }
    payload_bytes = _canonical_json(payload).encode()
    sig = private_key.sign(
        payload_bytes,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return SignedAgentCard(
        card=card,
        signature={
            "alg": "RS256",
            "kid": kid,
            "value": _b64url(sig),
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        },
    )


def verify_agent_card_rs256(
    signed: SignedAgentCard,
    *,
    public_key_pem: bytes | str,
) -> tuple[bool, str]:
    """Verify an RS256-signed ``SignedAgentCard``."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.exceptions import InvalidSignature
    except ImportError as e:
        raise ImportError(
            "cryptography required for RS256 verify"
        ) from e

    sig = signed.signature
    if not sig:
        return False, "no signature"
    if sig.get("alg") != "RS256":
        return False, f"unsupported alg: {sig.get('alg')}"
    expires = sig.get("expires_at")
    if expires is None or expires < time.time():
        return False, "signature expired"

    if isinstance(public_key_pem, str):
        public_key_pem = public_key_pem.encode()
    public_key = serialization.load_pem_public_key(public_key_pem)

    payload = {
        "card": signed.card.to_dict(),
        "issued_at": sig.get("issued_at"),
        "expires_at": expires,
        "kid": sig.get("kid", "default"),
    }
    payload_bytes = _canonical_json(payload).encode()
    try:
        public_key.verify(
            _b64url_decode(sig.get("value", "")),
            payload_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True, ""
    except InvalidSignature:
        return False, "signature mismatch"
    except Exception as e:
        return False, f"verification failed: {e}"


# -------------------- Helpers --------------------

def _canonical_json(d: dict[str, Any]) -> str:
    """Canonical JSON for stable signing — sorted keys, no whitespace."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


__all__ = [
    "TaskStreamEvent",
    "StreamingA2AServer",
    "SignedAgentCard",
    "sign_agent_card_hs256",
    "verify_agent_card_hs256",
    "sign_agent_card_rs256",
    "verify_agent_card_rs256",
]
