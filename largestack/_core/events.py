"""Async event bus with pub/sub and wildcard support."""
from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger("largestack.events")

class EventBus:
    def __init__(self):
        self._h: dict[str, list[Callable]] = defaultdict(list)
        self._mw: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable): self._h[event].append(handler)
    def off(self, event: str, handler: Callable):
        if handler in self._h[event]: self._h[event].remove(handler)

    def middleware(self, event: str):
        def dec(fn): self._mw[event].append(fn); return fn
        return dec

    async def emit(self, event: str, data: dict[str, Any] | None = None):
        data = {**(data or {}), "_event": event}
        for mw in self._mw.get(event, []):
            try: data = await mw(data) if asyncio.iscoroutinefunction(mw) else mw(data)
            except Exception as e: log.error(f"MW error {event}: {e}")
        for h in self._h.get(event, []) + self._h.get("*", []):
            try:
                if asyncio.iscoroutinefunction(h): await h(data)
                else: h(data)
            except Exception as e: log.error(f"Handler error {event}: {e}")

bus = EventBus()
