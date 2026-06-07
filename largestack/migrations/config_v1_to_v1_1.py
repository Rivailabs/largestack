"""Migrate v1 YAML config files to the v1.1-compatible shape."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CURRENT_SCHEMA_VERSION = "1.1"
DEFAULTS = {
    "schema_version": CURRENT_SCHEMA_VERSION,
    "default_llm": "openai/gpt-4o-mini",
    "max_turns": 25,
    "cost_budget": 5.0,
    "trace_enabled": True,
    "guardrails_enabled": True,
}


def _load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {p}")
    return data


def migrate_config(path: str | Path, *, write: bool = False) -> dict[str, Any]:
    """Return a v1.1-compatible config; optionally write it back."""
    p = Path(path)
    data = _load(p)
    migrated = dict(DEFAULTS)
    migrated.update(data)
    migrated["schema_version"] = str(migrated.get("schema_version") or CURRENT_SCHEMA_VERSION)
    if migrated["schema_version"] in {"1", "1.0"}:
        migrated["schema_version"] = CURRENT_SCHEMA_VERSION
    if "llm" in migrated and "default_llm" not in data:
        migrated["default_llm"] = migrated.pop("llm")
    if write:
        p.write_text(yaml.safe_dump(migrated, sort_keys=False), encoding="utf-8")
    return migrated


def check_config(path: str | Path) -> dict[str, Any]:
    data = migrate_config(path, write=False)
    missing = [k for k in DEFAULTS if k not in data]
    return {
        "path": str(path),
        "ok": not missing,
        "missing": missing,
        "schema_version": data.get("schema_version"),
    }
