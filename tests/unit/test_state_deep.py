"""Deep tests for state management."""

import asyncio, sys, os, tempfile

sys.path.insert(0, ".")


def test_checkpoint_save_load():
    from largestack._state.checkpoint import CheckpointManager

    mgr = CheckpointManager(os.path.join(tempfile.mkdtemp(), "ckpt.db"))
    state = {"step": 3, "data": [1, 2, 3]}
    mgr.save("w1", "step3", state)
    loaded = mgr.load("w1", "step3")
    assert loaded is not None
    assert loaded["step"] == 3


def test_checkpoint_overwrite():
    from largestack._state.checkpoint import CheckpointManager

    mgr = CheckpointManager(os.path.join(tempfile.mkdtemp(), "ckpt.db"))
    mgr.save("w1", "s1", {"v": 1})
    mgr.save("w1", "s1", {"v": 2})
    assert mgr.load("w1", "s1")["v"] == 2


def test_checkpoint_missing():
    from largestack._state.checkpoint import CheckpointManager

    mgr = CheckpointManager(os.path.join(tempfile.mkdtemp(), "ckpt.db"))
    assert mgr.load("w1", "nonexistent") is None


def test_checkpoint_latest():
    from largestack._state.checkpoint import CheckpointManager

    mgr = CheckpointManager(os.path.join(tempfile.mkdtemp(), "ckpt.db"))
    mgr.save("w1", "s1", {"v": 1})
    mgr.save("w1", "s2", {"v": 2})
    latest = mgr.load_latest("w1")
    assert latest is not None


def test_durable_step_once():
    from largestack._state.durable import DurableWorkflow

    d = DurableWorkflow("test-wf", os.path.join(tempfile.mkdtemp(), "dur.db"))
    call_count = 0

    async def my_step():
        nonlocal call_count
        call_count += 1
        return "result"

    r1 = asyncio.run(d.step("s1", my_step))
    r2 = asyncio.run(d.step("s1", my_step))
    assert r1 == "result"
    assert r2 == "result"
    assert call_count == 1
