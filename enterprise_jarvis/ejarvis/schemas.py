"""Typed (Pydantic) outputs — the agent returns validated models, not raw dicts."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TicketTriage(BaseModel):
    category: str = Field(description="one of: hr, it, security, other")
    priority: str = Field(description="one of: low, medium, high")
    summary: str = Field(description="one-line summary of the request")
    needs_approval: bool = Field(description="true if resolving it needs a human approval")
