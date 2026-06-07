"""Human-in-the-loop — agents can pause and request human input.

@tool
async def ask_human(question: str) -> str:
    return await hitl.request(question)
"""

from __future__ import annotations
import asyncio, logging, uuid
from typing import Any, Callable

log = logging.getLogger("largestack.hitl")


class HumanInTheLoop:
    """Enable agents to request human input mid-execution.

    Backends:
        - terminal: input() prompt (development)
        - callback: custom function (webhook, Slack, email)
        - queue: async queue for web UIs
    """

    def __init__(self, backend: str = "terminal", callback: Callable = None, timeout: float = 300):
        self.backend = backend
        self.callback = callback
        self.timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}
        self._queue: asyncio.Queue = asyncio.Queue()

    async def request(self, question: str, context: dict = None) -> str:
        """Request human input. Blocks until response received or timeout."""
        request_id = str(uuid.uuid4())[:8]
        log.info(f"HITL request [{request_id}]: {question}")

        if self.backend == "terminal":
            return await self._terminal_request(question)
        elif self.backend == "callback" and self.callback:
            return await self._callback_request(question, context)
        elif self.backend == "queue":
            return await self._queue_request(request_id, question)
        else:
            raise RuntimeError(f"Unknown HITL backend: {self.backend}")

    async def _terminal_request(self, question: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: input(f"\n🤖 Agent asks: {question}\n👤 Your response: ")
        )

    async def _callback_request(self, question: str, context: dict = None) -> str:
        if asyncio.iscoroutinefunction(self.callback):
            return await asyncio.wait_for(
                self.callback(question, context or {}), timeout=self.timeout
            )
        return self.callback(question, context or {})

    async def _queue_request(self, request_id: str, question: str) -> str:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._queue.put({"id": request_id, "question": question})
        try:
            return await asyncio.wait_for(future, timeout=self.timeout)
        finally:
            self._pending.pop(request_id, None)

    def respond(self, request_id: str, answer: str):
        """Submit human response (for queue/webhook backends)."""
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(answer)

    def create_tool(self):
        """Create a @tool-decorated function for agent use."""
        from largestack._core.tools import tool

        hitl = self

        @tool(timeout=self.timeout)
        async def ask_human(question: str) -> str:
            """Pause execution and ask a human for input or approval."""
            return await hitl.request(question)

        return ask_human
