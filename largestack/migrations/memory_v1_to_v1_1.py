"""Migrate serialized conversation memory into canonical v1.1 records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CURRENT_SCHEMA_VERSION = "1.1"


def _normalise_message(item: Any) -> dict[str, str]:
    if isinstance(item, dict):
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        return {"role": role, "content": content}
    return {"role": "user", "content": str(item)}


def migrate_memory(path: str | Path, *, write: bool = False) -> dict[str, Any]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    if isinstance(raw, dict):
        messages = raw.get("messages", [])
        tenant_id = raw.get("tenant_id") or raw.get("tenant")
        user_id = raw.get("user_id") or raw.get("user")
    elif isinstance(raw, list):
        messages = raw
        tenant_id = None
        user_id = None
    else:
        raise ValueError("Memory JSON must be a list or object")
    migrated = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "messages": [_normalise_message(m) for m in messages],
    }
    if write:
        p.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
    return migrated


def check_memory(path: str | Path) -> dict[str, Any]:
    data = migrate_memory(path, write=False)
    ok = isinstance(data.get("messages"), list) and all("role" in m and "content" in m for m in data["messages"])
    return {"path": str(path), "ok": ok, "message_count": len(data.get("messages", [])), "schema_version": data.get("schema_version")}
