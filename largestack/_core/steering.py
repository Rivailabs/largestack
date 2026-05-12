"""Steering hooks — programmatic agent control (inspired by AWS Strands steering hooks)."""
from __future__ import annotations
import asyncio
from typing import Any, Callable
from largestack.types import SteeringAction, SteeringResult

def proceed() -> SteeringResult: return SteeringResult(action=SteeringAction.PROCEED)
def guide(fb: str) -> SteeringResult: return SteeringResult(action=SteeringAction.GUIDE, feedback=fb)
def interrupt(result: Any = None) -> SteeringResult: return SteeringResult(action=SteeringAction.INTERRUPT, result=result)
def accept() -> SteeringResult: return SteeringResult(action=SteeringAction.ACCEPT)
def discard(fb: str) -> SteeringResult: return SteeringResult(action=SteeringAction.DISCARD, feedback=fb)

def steer_before_tool(fn): fn._largestack_steer = "before_tool"; return fn
def steer_after_model(fn): fn._largestack_steer = "after_model"; return fn

class SteeringEngine:
    def __init__(self, hooks: list[Callable] | None = None):
        self.before = [h for h in (hooks or []) if getattr(h, "_largestack_steer", "") == "before_tool"]
        self.after = [h for h in (hooks or []) if getattr(h, "_largestack_steer", "") == "after_model"]

    async def run_before(self, tool_name: str, params: dict, ctx: dict) -> SteeringResult:
        for h in self.before:
            r = await h(tool_name, params, ctx) if asyncio.iscoroutinefunction(h) else h(tool_name, params, ctx)
            if r.action != SteeringAction.PROCEED: return r
        return proceed()

    async def run_after(self, response: Any, ctx: dict) -> SteeringResult:
        for h in self.after:
            r = await h(response, ctx) if asyncio.iscoroutinefunction(h) else h(response, ctx)
            if r.action not in (SteeringAction.ACCEPT, SteeringAction.PROCEED): return r
        return accept()
