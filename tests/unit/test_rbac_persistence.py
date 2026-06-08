"""RBAC persistence regression tests (v0.4.0).

Validates that user records survive restarts when ``db_path`` is set,
and that the in-memory hot-path API stays unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def test_rbac_no_persistence_when_no_db_path():
    """Default in-memory behavior unchanged — no DB file created."""
    from largestack._enterprise.rbac import RBAC

    r = RBAC()
    r.add_user("alice", roles=["admin"])
    assert r.get_user("alice") is not None
    assert r._db_path is None


def test_rbac_persists_users_to_disk(tmp_path):
    """add_user writes through to SQLite."""
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"
    r = RBAC(db_path=str(db))
    r.add_user("alice", roles=["admin"], custom_permissions={"agent.run"})
    r.add_user("bob", roles=["viewer"])

    assert db.exists(), "DB file not created"
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT user_id FROM rbac_users ORDER BY user_id").fetchall()
    conn.close()
    assert [row[0] for row in rows] == ["alice", "bob"]


def test_rbac_loads_users_on_init(tmp_path):
    """A new RBAC pointed at an existing DB picks up the users."""
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"

    # First instance — populate
    r1 = RBAC(db_path=str(db))
    r1.add_user("alice", roles=["admin"])
    r1.add_user("carol", roles=["developer"], custom_permissions={"experimental.preview"})

    # Second instance — fresh, just reads from disk
    r2 = RBAC(db_path=str(db))
    alice = r2.get_user("alice")
    carol = r2.get_user("carol")
    assert alice is not None
    assert "admin" in alice.roles
    assert carol is not None
    assert "developer" in carol.roles
    assert "experimental.preview" in carol.custom_permissions

    # Permission checks survive restart
    assert r2.check("alice", "anything")  # admin wildcard
    assert r2.check("carol", "experimental.preview")


def test_rbac_remove_user_deletes_from_disk(tmp_path):
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"
    r = RBAC(db_path=str(db))
    r.add_user("alice", roles=["admin"])
    r.add_user("bob", roles=["viewer"])

    assert r.remove_user("alice")

    conn = sqlite3.connect(db)
    remaining = [row[0] for row in conn.execute("SELECT user_id FROM rbac_users").fetchall()]
    conn.close()
    assert remaining == ["bob"]

    # Reload — alice is gone
    r2 = RBAC(db_path=str(db))
    assert r2.get_user("alice") is None
    assert r2.get_user("bob") is not None


def test_rbac_grant_revoke_role_writes_through(tmp_path):
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"
    r = RBAC(db_path=str(db))
    r.add_user("alice", roles=["viewer"])
    r.grant_role("alice", "developer")

    # Reload — alice has both roles
    r2 = RBAC(db_path=str(db))
    alice = r2.get_user("alice")
    assert "viewer" in alice.roles
    assert "developer" in alice.roles

    # Revoke and reload again
    r2.revoke_role("alice", "viewer")
    r3 = RBAC(db_path=str(db))
    alice = r3.get_user("alice")
    assert "viewer" not in alice.roles
    assert "developer" in alice.roles


def test_rbac_assign_role_persists_for_new_and_existing(tmp_path):
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"
    r = RBAC(db_path=str(db))

    # New user via assign_role
    r.assign_role("eve", "viewer")
    # Existing user via assign_role
    r.add_user("frank", roles=["viewer"])
    r.assign_role("frank", "developer")

    r2 = RBAC(db_path=str(db))
    assert "viewer" in r2.get_user("eve").roles
    assert {"viewer", "developer"}.issubset(r2.get_user("frank").roles)


def test_rbac_load_skips_malformed_rows(tmp_path, caplog):
    """Garbage rows in the DB don't crash startup."""
    import logging
    from largestack._enterprise.rbac import RBAC

    db = tmp_path / "rbac.db"

    # Initialize schema by creating a real instance once
    RBAC(db_path=str(db))

    # Corrupt a row directly
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO rbac_users (user_id, roles, custom_permissions, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("bad_user", "not-json{{{", "[]", 0.0, 0.0),
    )
    conn.execute(
        "INSERT INTO rbac_users (user_id, roles, custom_permissions, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("good_user", '["admin"]', "[]", 0.0, 0.0),
    )
    conn.commit()
    conn.close()

    caplog.set_level(logging.WARNING, logger="largestack.rbac")
    r = RBAC(db_path=str(db))
    # Bad row skipped, good row loaded
    assert r.get_user("bad_user") is None
    assert r.get_user("good_user") is not None


def test_rbac_db_path_expanduser(tmp_path, monkeypatch):
    """~/ in db_path is expanded."""
    from largestack._enterprise.rbac import RBAC

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows: expanduser uses USERPROFILE
    r = RBAC(db_path="~/rbac.db")
    r.add_user("alice", roles=["admin"])
    assert (tmp_path / "rbac.db").exists()
