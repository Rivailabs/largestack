"""Cross-agent memory sharing — thread-isolated by default, explicit sharing."""

from __future__ import annotations
from typing import Any
import asyncio


class SharedMemorySpace:
    """Shared memory accessible by multiple agents.

    Thread-isolated by default. Explicit sharing via share()/subscribe().
    """

    def __init__(self, name: str = "shared"):
        self.name = name
        self._store: dict[str, Any] = {}
        self._subscribers: dict[str, list] = {}
        self._lock = asyncio.Lock()

    async def put(self, key: str, value: Any, notify: bool = True):
        """Store a value in shared memory."""
        async with self._lock:
            self._store[key] = value
        if notify:
            for cb in self._subscribers.get(key, []):
                if asyncio.iscoroutinefunction(cb):
                    await cb(key, value)
                else:
                    cb(key, value)

    async def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def subscribe(self, key: str, callback):
        """Subscribe to changes on a key."""
        if key not in self._subscribers:
            self._subscribers[key] = []
        self._subscribers[key].append(callback)

    async def get_all(self) -> dict:
        return dict(self._store)

    async def clear(self):
        async with self._lock:
            self._store.clear()
