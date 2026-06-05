"""Role-based access control: which roles may invoke which tools/actions."""
from __future__ import annotations

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "kb_search", "remember", "recall", "calculate",
        "submit_approval", "list_approvals", "raise_ticket", "read_audit",
    },
    "agent": {
        "kb_search", "remember", "recall", "calculate",
        "submit_approval", "list_approvals", "raise_ticket",
    },
    "viewer": {"kb_search", "recall", "calculate"},
}


def can(role: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role, set())
