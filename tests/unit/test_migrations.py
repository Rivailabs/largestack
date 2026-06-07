"""Production migration helpers stay deterministic and idempotent."""

from __future__ import annotations

import json
import shutil
import sqlite3


def test_config_migration_maps_legacy_llm(tmp_path):
    from largestack.migrations import migrate_config, check_config

    src = tmp_path / "largestack.yaml"
    shutil.copyfile("tests/fixtures/migration/v1_config.yaml", src)
    migrated = migrate_config(src, write=True)

    assert migrated["schema_version"] == "1.1"
    assert migrated["default_llm"] == "deepseek/deepseek-chat"
    assert check_config(src)["ok"] is True
    assert "\nllm:" not in "\n" + src.read_text(encoding="utf-8")


def test_memory_migration_normalizes_legacy_list(tmp_path):
    from largestack.migrations import migrate_memory, check_memory

    src = tmp_path / "memory.json"
    shutil.copyfile("tests/fixtures/migration/v1_memory.json", src)
    migrated = migrate_memory(src, write=True)

    assert migrated["schema_version"] == "1.1"
    assert migrated["messages"][0] == {"role": "user", "content": "hello"}
    assert migrated["messages"][1] == {"role": "user", "content": "legacy note"}
    assert check_memory(src)["ok"] is True
    assert json.loads(src.read_text(encoding="utf-8"))["schema_version"] == "1.1"


def test_trace_db_migration_adds_dashboard_columns(tmp_path):
    from largestack.migrations import migrate_trace_db

    db = tmp_path / "traces.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE traces (trace_id TEXT PRIMARY KEY, agent TEXT)")
    dry = migrate_trace_db(db, write=False)
    assert "task" in dry["missing"]

    applied = migrate_trace_db(db, write=True)
    assert applied["ok"] is True
    assert "task" in applied["columns"]
    assert "duration_ms" in applied["columns"]


def test_project_migration_runs_all_known_artifacts(tmp_path):
    from largestack.migrations import apply_project_migrations, check_project

    shutil.copyfile("tests/fixtures/migration/v1_config.yaml", tmp_path / "largestack.yaml")
    shutil.copyfile("tests/fixtures/migration/v1_memory.json", tmp_path / "memory.json")
    with sqlite3.connect(tmp_path / "traces.db") as conn:
        conn.execute("CREATE TABLE traces (trace_id TEXT PRIMARY KEY)")

    assert check_project(tmp_path)["ok"] is False
    result = apply_project_migrations(tmp_path)
    assert result["ok"] is True
    assert set(result["applied"]) == {"config", "memory", "trace_db"}
    assert check_project(tmp_path)["ok"] is True
