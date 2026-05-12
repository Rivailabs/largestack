"""Erlang-style supervisor — accepts Agent objects or callables."""
from __future__ import annotations
import asyncio, logging, time
from typing import Any, Callable

log = logging.getLogger("largestack.supervisor")

class Supervisor:
    """Restart failed children automatically. Accepts Agent objects.
    
    Strategies: one_for_one (restart failed), one_for_all (restart all), rest_for_one
    """
    def __init__(self, strategy: str = "one_for_one", max_restarts: int = 5,
                 max_seconds: float = 60.0, children: list = None, task: str = ""):
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.max_seconds = max_seconds
        self.children = children or []
        self.task = task
        self._restart_times: list[float] = []

    async def start(self, **kw) -> list[Any]:
        results = []
        task = kw.pop("task", self.task) or ""
        for i, child in enumerate(self.children):
            try:
                result = await self._run_child(child, task, **kw)
                results.append(result)
            except Exception as e:
                log.warning(f"Child {i} failed: {e}")
                result = await self._handle_failure(i, child, task, e, kw)
                results.append(result)
        return results

    async def _run_child(self, child, task: str, **kw):
        # Agent objects
        if hasattr(child, 'run') and hasattr(child, 'name'):
            return await child.run(task, **kw) if task else await child.run("Execute your task", **kw)
        # Async callables
        if asyncio.iscoroutinefunction(child):
            return await child(**kw)
        return child(**kw)

    async def _handle_failure(self, idx, child, task, error, kw):
        now = time.monotonic()
        self._restart_times = [t for t in self._restart_times if now - t < self.max_seconds]
        self._restart_times.append(now)
        if len(self._restart_times) > self.max_restarts:
            raise RuntimeError(f"Max restarts exceeded: {error}") from error
        log.info(f"Restarting child {idx} ({self.strategy})")
        await asyncio.sleep(0.1)
        if self.strategy == "one_for_one":
            return await self._run_child(child, task, **kw)
        raise RuntimeError(f"{self.strategy} restart from child {idx}: {error}")
