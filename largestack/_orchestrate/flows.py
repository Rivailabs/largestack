"""Event-driven flows — @start/@listen decorators (CrewAI pattern)."""
from __future__ import annotations
import asyncio
from typing import Any, Callable
from largestack._core.events import EventBus

class Flow:
    """Event-driven orchestration with @start and @listen decorators."""
    def __init__(self, name: str = "flow"):
        self.name = name
        self._bus = EventBus()
        self._start_fn: Callable | None = None
        self._listeners: dict[str, list[Callable]] = {}
    
    def start(self, fn: Callable) -> Callable:
        """Mark function as flow entry point."""
        self._start_fn = fn
        return fn
    
    def listen(self, event: str):
        """Listen for event and trigger handler."""
        def decorator(fn):
            if event not in self._listeners:
                self._listeners[event] = []
            self._listeners[event].append(fn)
            return fn
        return decorator
    
    async def run(self, initial_input: Any = None) -> Any:
        """Execute the flow starting from @start."""
        if not self._start_fn:
            raise RuntimeError("No @start function defined")
        
        # Register listeners
        for event, handlers in self._listeners.items():
            for handler in handlers:
                self._bus.on(event, handler)
        
        # Run start function
        result = self._start_fn(initial_input) if not asyncio.iscoroutinefunction(self._start_fn) \
            else await self._start_fn(initial_input)
        return result

    async def emit(self, event: str, data: Any = None):
        await self._bus.emit(event, {"data": data})
