"""Project-level migration checks."""

from __future__ import annotations

from pathlib import Path

from .config_v1_to_v1_1 import check_config, migrate_config
from .memory_v1_to_v1_1 import check_memory, migrate_memory
from .trace_db_v1_to_v1_1 import check_trace_db, migrate_trace_db


def check_project(root: str | Path = ".") -> dict[str, object]:
    root = Path(root)
    results: dict[str, object] = {"root": str(root), "checks": []}
    checks = results["checks"]
    config = root / "largestack.yaml"
    if config.exists():
        checks.append({"kind": "config", **check_config(config)})
    memory = root / "memory.json"
    if memory.exists():
        checks.append({"kind": "memory", **check_memory(memory)})
    trace_db = root / "traces.db"
    if trace_db.exists():
        checks.append({"kind": "trace_db", **check_trace_db(trace_db)})
    results["ok"] = all(c.get("ok", True) for c in checks) if checks else True
    return results


def apply_project_migrations(root: str | Path = ".") -> dict[str, object]:
    root = Path(root)
    applied = []
    config = root / "largestack.yaml"
    if config.exists():
        migrate_config(config, write=True)
        applied.append("config")
    memory = root / "memory.json"
    if memory.exists():
        migrate_memory(memory, write=True)
        applied.append("memory")
    trace_db = root / "traces.db"
    if trace_db.exists():
        migrate_trace_db(trace_db, write=True)
        applied.append("trace_db")
    return {"root": str(root), "applied": applied, "ok": True}
