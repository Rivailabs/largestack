"""Event replay — record and replay agent event streams for debugging."""

from __future__ import annotations
import json, os, time
from typing import Any


class EventRecorder:
    """Record all agent events for replay debugging."""

    def __init__(self, path: str = None):
        self.path = path
        self._events: list[dict] = []
        self._recording = False

    def start(self):
        self._events = []
        self._recording = True
        self._t0 = time.monotonic()

    def record(self, event_type: str, data: dict):
        if self._recording:
            self._events.append(
                {
                    "type": event_type,
                    "data": data,
                    "offset_ms": (time.monotonic() - self._t0) * 1000,
                    "timestamp": time.time(),
                }
            )

    def stop(self) -> list[dict]:
        self._recording = False
        if self.path:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self._events, f, indent=2, default=str)
        return self._events


class EventReplayer:
    """Replay recorded events with optional speed control."""

    def __init__(self, events: list[dict] = None, path: str = None):
        if path:
            with open(path) as f:
                self._events = json.load(f)
        else:
            self._events = events or []
        self._index = 0

    async def replay(self, speed: float = 1.0, callback=None):
        """Replay events with timing. speed=2.0 means 2x faster."""
        import asyncio

        prev_offset = 0
        for event in self._events:
            offset = event.get("offset_ms", 0)
            delay = (offset - prev_offset) / 1000 / speed
            if delay > 0:
                await asyncio.sleep(delay)
            if callback:
                await callback(event) if asyncio.iscoroutinefunction(callback) else callback(event)
            prev_offset = offset

    def get_events(self, event_type: str = None) -> list[dict]:
        if event_type:
            return [e for e in self._events if e["type"] == event_type]
        return list(self._events)
