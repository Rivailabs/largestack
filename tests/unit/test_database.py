"""Tests for database abstraction."""

import os, sys, tempfile

sys.path.insert(0, ".")


def test_sqlite_create():
    from largestack._core.database import Database

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    assert db.backend == "sqlite"


def test_sqlite_crud():
    from largestack._core.database import Database

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    db.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO test (name) VALUES (?)", ("hello",))
    db.commit()
    row = db.fetchone("SELECT * FROM test WHERE name=?", ("hello",))
    assert row["name"] == "hello"


def test_sqlite_fetchall():
    from largestack._core.database import Database

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    db.execute("CREATE TABLE t (v TEXT)")
    db.execute("INSERT INTO t VALUES (?)", ("a",))
    db.execute("INSERT INTO t VALUES (?)", ("b",))
    db.commit()
    rows = db.fetchall("SELECT * FROM t")
    assert len(rows) == 2


def test_sqlite_transaction_commit():
    from largestack._core.database import Database

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    db.execute("CREATE TABLE t (v TEXT)")
    db.commit()
    with db.transaction():
        db.execute("INSERT INTO t VALUES (?)", ("x",))
    assert db.fetchone("SELECT * FROM t")["v"] == "x"


def test_sqlite_transaction_rollback():
    from largestack._core.database import Database

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    db.execute("CREATE TABLE t (v TEXT NOT NULL)")
    db.commit()
    try:
        with db.transaction():
            db.execute("INSERT INTO t VALUES (?)", ("good",))
            db.execute("INSERT INTO t VALUES (NULL)")  # Should fail
    except Exception:
        pass
    rows = db.fetchall("SELECT * FROM t")
    assert len(rows) == 0  # Rolled back


def test_migrations():
    from largestack._core.database import Database, run_migrations

    db = Database.create(f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}")
    run_migrations(db)
    # Should have created tables
    rows = db.fetchall("SELECT name FROM largestack_migrations")
    assert len(rows) >= 1


def test_placeholder_conversion():
    from largestack._core.database import PostgreSQLDatabase

    assert (
        PostgreSQLDatabase._convert_placeholders("SELECT * WHERE a=? AND b=?")
        == "SELECT * WHERE a=%s AND b=%s"
    )
    assert PostgreSQLDatabase._convert_placeholders("SELECT '?' FROM t") == "SELECT '?' FROM t"
