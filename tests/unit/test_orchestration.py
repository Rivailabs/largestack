"""Tests for orchestration patterns."""

import asyncio
from largestack._orchestrate.dag import DAGWorkflow
from largestack._orchestrate.state_machine import StateMachine
from largestack._orchestrate.sequential import SequentialPipeline
from largestack._orchestrate.parallel import ParallelFanOut
from largestack._orchestrate.supervisor import Supervisor
from largestack._orchestrate.flows import Flow


def test_dag_simple():
    dag = DAGWorkflow()
    dag.add_node("a", lambda s: {**s, "a": True})
    dag.add_node("b", lambda s: {**s, "b": True}, deps=["a"])
    r = asyncio.run(dag.run({}))
    assert r["a"] and r["b"]


def test_dag_parallel():
    dag = DAGWorkflow()
    dag.add_node("root", lambda s: {**s, "v": 1})
    dag.add_node("left", lambda s: {**s, "left": s["v"] * 2}, deps=["root"])
    dag.add_node("right", lambda s: {**s, "right": s["v"] * 3}, deps=["root"])
    dag.add_node("merge", lambda s: {**s, "total": s["left"] + s["right"]}, deps=["left", "right"])
    r = asyncio.run(dag.run({}))
    assert r["total"] == 5


def test_state_machine_cyclic():
    sm = StateMachine()
    sm.add_node("count", lambda s: {**s, "n": s.get("n", 0) + 1})
    sm.add_node("done", lambda s: s)
    sm.add_edge("count", "count", lambda s: s["n"] < 5)
    sm.add_edge("count", "done", lambda s: s["n"] >= 5)
    sm.set_end("done")
    r = asyncio.run(sm.run({}))
    assert r["n"] == 5


def test_state_machine_max_transitions():
    sm = StateMachine(max_transitions=3)
    sm.add_node("loop", lambda s: {**s, "n": s.get("n", 0) + 1})
    sm.add_edge("loop", "loop")  # Infinite loop
    r = asyncio.run(sm.run({}))
    assert r["n"] == 3


def test_supervisor_one_for_one():
    results = []

    async def good_child(**kw):
        results.append("ok")
        return "ok"

    s = Supervisor(strategy="one_for_one", children=[good_child, good_child])
    asyncio.run(s.start())
    assert len(results) == 2


def test_flow():
    flow = Flow("test")
    executed = []

    @flow.start
    def begin(data):
        executed.append("start")
        return data

    assert len(executed) == 0
    asyncio.run(flow.run("input"))
    assert "start" in executed
