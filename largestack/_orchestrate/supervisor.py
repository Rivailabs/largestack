"""Erlang-style supervisor — accepts Agent objects or callables."""

from __future__ import annotations
import asyncio, logging, time
from typing import Any, Callable

log = logging.getLogger("largestack.supervisor")


class Supervisor:
    """Restart failed children automatically. Accepts Agent objects.

    Strategies: one_for_one (restart failed), one_for_all (restart all), rest_for_one
    """

    def __init__(
        self,
        strategy: str = "one_for_one",
        max_restarts: int = 5,
        max_seconds: float = 60.0,
        children: list = None,
        task: str = "",
    ):
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.max_seconds = max_seconds
        self.children = children or []
        self.task = task
        self._restart_times: list[float] = []

    async def start(self, **kw) -> list[Any]:
        # v1.1.1: implement all three documented strategies (was: one_for_one only,
        # the others raised). Index-driven loop so a failure can restart from the
        # right child per strategy. Restart budget bounds infinite restart loops.
        task = kw.pop("task", self.task) or ""
        results: list[Any] = [None] * len(self.children)
        i = 0
        while i < len(self.children):
            child = self.children[i]
            try:
                results[i] = await self._run_child(child, task, **kw)
                i += 1
            except Exception as e:
                log.warning(f"Child {i} failed: {e}")
                # _handle_failure returns the index to (re)start from, or raises
                # when the restart budget is exhausted / strategy is unknown.
                i = await self._handle_failure(i, e)
        return results

    async def _run_child(self, child, task: str, **kw):
        # Agent objects
        if hasattr(child, "run") and hasattr(child, "name"):
            return (
                await child.run(task, **kw) if task else await child.run("Execute your task", **kw)
            )
        # Async callables
        if asyncio.iscoroutinefunction(child):
            return await child(**kw)
        return child(**kw)

    async def _handle_failure(self, idx, error) -> int:
        now = time.monotonic()
        self._restart_times = [t for t in self._restart_times if now - t < self.max_seconds]
        self._restart_times.append(now)
        if len(self._restart_times) > self.max_restarts:
            raise RuntimeError(f"Max restarts exceeded: {error}") from error
        await asyncio.sleep(0.1)
        if self.strategy == "one_for_all":
            # Terminate + restart every child from the beginning.
            log.info(f"Restarting ALL children (one_for_all) after child {idx} failed")
            return 0
        if self.strategy == "rest_for_one":
            # Restart the failed child and all children started after it. In this
            # sequential model, children after idx haven't started, so this restarts
            # from idx (the failed child) onward.
            log.info(f"Restarting child {idx} and the rest (rest_for_one)")
            return idx
        if self.strategy == "one_for_one":
            log.info(f"Restarting child {idx} (one_for_one)")
            return idx
        raise RuntimeError(f"Unknown supervisor strategy: {self.strategy!r}") from error
