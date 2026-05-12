"""Time-travel / checkpointing for Graph workflow state (v0.9.0).

Lets you persist Graph state at each node and replay/branch from any
prior checkpoint. Closes the LangGraph "time-travel" gap.

Two backends:
- ``MemoryCheckpointStore`` — in-process, for testing
- ``RedisCheckpointStore`` — Redis-backed, production-grade

Both implement ``CheckpointStore`` ABC.
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any

log = logging.getLogger("largestack.checkpoint")


@dataclass
class Checkpoint:
    """One checkpoint of graph state."""
    thread_id: str          # logical session/conversation ID
    checkpoint_id: str      # unique ID for this checkpoint
    node_name: str          # which node just completed
    state: dict             # state snapshot
    parent_id: str = ""     # ID of previous checkpoint
    metadata: dict = field(default_factory=dict)
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(
            thread_id=d.get("thread_id", ""),
            checkpoint_id=d.get("checkpoint_id", ""),
            node_name=d.get("node_name", ""),
            state=d.get("state", {}),
            parent_id=d.get("parent_id", ""),
            metadata=d.get("metadata", {}),
            timestamp=float(d.get("timestamp", 0.0)),
        )


class CheckpointStore(ABC):
    """ABC for checkpoint storage."""

    @abstractmethod
    async def save(self, checkpoint: Checkpoint) -> None:
        ...

    @abstractmethod
    async def load(self, thread_id: str, checkpoint_id: str) -> Checkpoint | None:
        ...

    @abstractmethod
    async def list_for_thread(self, thread_id: str) -> list[Checkpoint]:
        ...

    @abstractmethod
    async def latest(self, thread_id: str) -> Checkpoint | None:
        ...

    @abstractmethod
    async def delete_thread(self, thread_id: str) -> int:
        ...


# -------------------- Memory backend --------------------

class MemoryCheckpointStore(CheckpointStore):
    """In-process checkpoint store. Loses data on restart."""

    def __init__(self):
        # thread_id -> {checkpoint_id: Checkpoint}
        self._data: dict[str, dict[str, Checkpoint]] = {}
        self._lock = asyncio.Lock()

    async def save(self, checkpoint: Checkpoint) -> None:
        async with self._lock:
            self._data.setdefault(checkpoint.thread_id, {})[
                checkpoint.checkpoint_id
            ] = checkpoint

    async def load(self, thread_id: str, checkpoint_id: str) -> Checkpoint | None:
        async with self._lock:
            return self._data.get(thread_id, {}).get(checkpoint_id)

    async def list_for_thread(self, thread_id: str) -> list[Checkpoint]:
        async with self._lock:
            cps = list(self._data.get(thread_id, {}).values())
            cps.sort(key=lambda c: c.timestamp)
            return cps

    async def latest(self, thread_id: str) -> Checkpoint | None:
        async with self._lock:
            cps = self._data.get(thread_id, {})
            if not cps:
                return None
            return max(cps.values(), key=lambda c: c.timestamp)

    async def delete_thread(self, thread_id: str) -> int:
        async with self._lock:
            n = len(self._data.get(thread_id, {}))
            self._data.pop(thread_id, None)
            return n


# -------------------- Redis backend --------------------

class RedisCheckpointStore(CheckpointStore):
    """Redis-backed checkpoint store.

    Uses two keys per thread:
    - ``largestack:cp:{thread_id}:{checkpoint_id}`` — JSON checkpoint
    - ``largestack:cp:idx:{thread_id}`` — sorted set of checkpoint_ids by timestamp

    Args:
        url: Redis URL.
        prefix: key prefix (default ``largestack:cp:``).
        ttl_seconds: optional auto-expiry per key.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        *,
        prefix: str = "largestack:cp:",
        ttl_seconds: int | None = None,
    ):
        self.url = url
        self.prefix = prefix
        self.ttl = ttl_seconds
        self._client = None

    async def _connect(self):
        if self._client is not None:
            return
        try:
            import redis.asyncio as redis_async
        except ImportError as e:
            raise ImportError(
                "RedisCheckpointStore needs: pip install 'redis>=5.0'"
            ) from e
        self._client = redis_async.from_url(self.url, decode_responses=True)

    def _key(self, thread_id: str, cp_id: str) -> str:
        return f"{self.prefix}{thread_id}:{cp_id}"

    def _idx_key(self, thread_id: str) -> str:
        return f"{self.prefix}idx:{thread_id}"

    async def save(self, checkpoint: Checkpoint) -> None:
        await self._connect()
        k = self._key(checkpoint.thread_id, checkpoint.checkpoint_id)
        payload = json.dumps(checkpoint.to_dict())
        await self._client.set(k, payload)
        if self.ttl:
            await self._client.expire(k, self.ttl)
        # Add to sorted index
        await self._client.zadd(
            self._idx_key(checkpoint.thread_id),
            {checkpoint.checkpoint_id: checkpoint.timestamp},
        )
        if self.ttl:
            await self._client.expire(self._idx_key(checkpoint.thread_id), self.ttl)

    async def load(self, thread_id: str, checkpoint_id: str) -> Checkpoint | None:
        await self._connect()
        raw = await self._client.get(self._key(thread_id, checkpoint_id))
        if not raw:
            return None
        try:
            return Checkpoint.from_dict(json.loads(raw))
        except Exception as e:
            log.debug(f"failed to parse checkpoint: {e}")
            return None

    async def list_for_thread(self, thread_id: str) -> list[Checkpoint]:
        await self._connect()
        ids = await self._client.zrange(self._idx_key(thread_id), 0, -1)
        out = []
        for cp_id in ids:
            cp = await self.load(thread_id, cp_id)
            if cp:
                out.append(cp)
        return out

    async def latest(self, thread_id: str) -> Checkpoint | None:
        await self._connect()
        ids = await self._client.zrange(self._idx_key(thread_id), -1, -1)
        if not ids:
            return None
        return await self.load(thread_id, ids[0])

    async def delete_thread(self, thread_id: str) -> int:
        await self._connect()
        ids = await self._client.zrange(self._idx_key(thread_id), 0, -1)
        if ids:
            keys = [self._key(thread_id, i) for i in ids]
            keys.append(self._idx_key(thread_id))
            await self._client.delete(*keys)
        return len(ids)


# -------------------- Helpers --------------------

def new_checkpoint_id() -> str:
    """Generate a unique checkpoint ID (timestamp + random)."""
    import secrets
    return f"cp_{int(time.time() * 1000)}_{secrets.token_hex(4)}"


async def checkpoint_node(
    store: CheckpointStore,
    thread_id: str,
    node_name: str,
    state: dict,
    *,
    parent_id: str = "",
    metadata: dict | None = None,
) -> Checkpoint:
    """Convenience: create + save a checkpoint."""
    cp = Checkpoint(
        thread_id=thread_id,
        checkpoint_id=new_checkpoint_id(),
        node_name=node_name,
        state=dict(state),
        parent_id=parent_id,
        metadata=metadata or {},
        timestamp=time.time(),
    )
    await store.save(cp)
    return cp
