"""Module-level helpers for tests/unit/test_p0_fixes_v0310.py.

Put dataclasses and decorated tools at module scope so `get_type_hints()`
inside `largestack.decorators._extract_tool_schema` can resolve forward
references.
"""
from __future__ import annotations
from dataclasses import dataclass

from largestack.decorators import RunContext


@dataclass
class _Deps:
    user_id: str


def make_search_tool(agent):
    """Attach a `search` tool to the given decorator-API agent."""
    @agent.tool
    async def search(ctx: RunContext[_Deps], query: str) -> str:
        """Search KB."""
        return f"hit:{query}:{ctx.deps.user_id}"
    return search
