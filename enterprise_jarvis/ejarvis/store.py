"""Tenant-scoped persistence: memory (facts), HITL approval queue, support
tickets, and an append-only audit log (JSONL). All on disk under DATA_DIR/<tenant>/.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tenant_dir(tenant: str) -> Path:
    safe = "".join(c for c in tenant if c.isalnum() or c in "-_") or "default"
    d = DATA_DIR / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ---- Memory (facts) --------------------------------------------------------

def set_fact(tenant: str, key: str, value: str) -> None:
    with _LOCK:
        p = _tenant_dir(tenant) / "facts.json"
        facts = _read(p, {})
        facts[key.strip().lower()] = value.strip()
        _write(p, facts)


def get_fact(tenant: str, key: str) -> str | None:
    with _LOCK:
        return _read(_tenant_dir(tenant) / "facts.json", {}).get(key.strip().lower())


# ---- HITL approval queue ---------------------------------------------------

def add_approval(tenant: str, user: str, action: str, details: str) -> int:
    with _LOCK:
        p = _tenant_dir(tenant) / "approvals.json"
        items = _read(p, [])
        rid = len(items) + 1
        items.append({
            "id": rid, "user": user, "action": action.strip(), "details": details.strip(),
            "status": "pending", "at": _now(),
        })
        _write(p, items)
        return rid


def get_approvals(tenant: str) -> list[dict[str, Any]]:
    with _LOCK:
        return _read(_tenant_dir(tenant) / "approvals.json", [])


# ---- Support tickets -------------------------------------------------------

def add_ticket(tenant: str, user: str, subject: str, body: str) -> str:
    with _LOCK:
        p = _tenant_dir(tenant) / "tickets.json"
        items = _read(p, [])
        tid = f"TKT-{len(items) + 1:04d}"
        items.append({"id": tid, "user": user, "subject": subject.strip(),
                      "body": body.strip(), "status": "open", "at": _now()})
        _write(p, items)
        return tid


# ---- Append-only audit log (JSONL) -----------------------------------------

def audit(tenant: str, user: str, role: str, event: str, detail: str = "") -> None:
    with _LOCK:
        p = _tenant_dir(tenant) / "audit.jsonl"
        line = json.dumps({"at": _now(), "user": user, "role": role,
                           "event": event, "detail": detail[:300]}, ensure_ascii=False)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_audit(tenant: str, limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        p = _tenant_dir(tenant) / "audit.jsonl"
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return out
