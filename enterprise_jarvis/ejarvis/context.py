"""The typed dependency injected into every agent run (RunContext[Principal])."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Principal:
    """The signed-in identity. Drives RBAC, multi-tenant scoping, and audit."""

    user: str
    role: str  # "admin" | "agent" | "viewer"
    tenant: str
    session_id: str = ""
