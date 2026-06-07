"""Token-level streaming via SSE and WebSocket."""

from __future__ import annotations
import asyncio, json
from typing import Any, AsyncIterator


class StreamHandler:
    """Handle streaming of agent responses."""

    def __init__(self):
        self._listeners: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._listeners.append(q)
        return q

    async def emit_token(self, token: str, metadata: dict = None):
        event = {"type": "token", "content": token, **(metadata or {})}
        for q in self._listeners:
            await q.put(event)

    async def emit_tool_call(self, tool_name: str, params: dict):
        for q in self._listeners:
            await q.put({"type": "tool_call", "name": tool_name, "params": params})

    async def emit_done(self, result: dict = None):
        for q in self._listeners:
            await q.put({"type": "done", **(result or {})})
            await q.put(None)  # Signal end

    async def sse_generator(self, agent, task: str):
        """Generate SSE events from agent execution."""
        async for token in agent.stream(task):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
