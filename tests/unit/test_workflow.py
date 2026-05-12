"""Tests for Workflow public API."""
import asyncio
from largestack.workflow import Workflow

def test_dag_workflow():
    wf = Workflow("test", mode="dag")
    wf.add_node("a", lambda s: {**s, "step": 1})
    wf.add_node("b", lambda s: {**s, "result": s["step"] * 10}, deps=["a"])
    r = asyncio.run(wf.run({}))
    assert r["result"] == 10

def test_state_machine_workflow():
    wf = Workflow("test", mode="state_machine")
    wf.add_node("start", lambda s: {**s, "n": s.get("n", 0) + 1})
    wf.add_node("end", lambda s: s)
    wf.add_edge("start", "end", lambda s: s["n"] >= 2)
    wf.add_edge("start", "start", lambda s: s["n"] < 2)
    wf.set_end("end")
    r = asyncio.run(wf.run({}))
    assert r["n"] == 2
