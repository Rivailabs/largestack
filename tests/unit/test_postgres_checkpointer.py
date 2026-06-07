"""Postgres checkpointer tests (async, uses SQLite fallback when PG unavailable)."""

import sys, os, tempfile, asyncio

sys.path.insert(0, ".")


def test_checkpointer_save_load_fallback():
    from largestack._state.postgres_checkpointer import PostgresCheckpointer

    os.environ["LARGESTACK_SQLITE_CHECKPOINT"] = os.path.join(tempfile.mkdtemp(), "ckpt.db")
    cp = PostgresCheckpointer(dsn=None)  # forces SQLite fallback
    cid = asyncio.run(cp.save("thread-1", {"step": 5, "data": [1, 2, 3]}))
    state = asyncio.run(cp.load("thread-1", cid))
    assert state is not None
    assert state["step"] == 5


def test_checkpointer_load_latest():
    from largestack._state.postgres_checkpointer import PostgresCheckpointer

    os.environ["LARGESTACK_SQLITE_CHECKPOINT"] = os.path.join(tempfile.mkdtemp(), "ckpt.db")
    cp = PostgresCheckpointer(dsn=None)
    asyncio.run(cp.save("t1", {"v": 1}, checkpoint_id="ck1"))
    asyncio.run(cp.save("t1", {"v": 2}, checkpoint_id="ck2"))
    latest = asyncio.run(cp.load("t1"))  # No cid → latest
    assert latest is not None
