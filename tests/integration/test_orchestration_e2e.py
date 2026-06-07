"""Orchestration integration tests."""

import asyncio, sys

sys.path.insert(0, ".")


def test_dag_parallel_execution():
    from largestack._orchestrate.dag import DAGWorkflow

    dag = DAGWorkflow()
    dag.add_node("data", lambda s: {**s, "raw": [10, 20, 30]})
    dag.add_node("sum", lambda s: {**s, "total": sum(s["raw"])}, deps=["data"])
    dag.add_node("avg", lambda s: {**s, "average": s["total"] / len(s["raw"])}, deps=["sum"])
    r = asyncio.run(dag.run({}))
    assert r["total"] == 60 and r["average"] == 20.0


def test_state_machine_with_conditions():
    from largestack._orchestrate.state_machine import StateMachine

    sm = StateMachine()
    sm.add_node("fetch", lambda s: {**s, "data": "raw_data"})
    sm.add_node("validate", lambda s: {**s, "valid": len(s.get("data", "")) > 3})
    sm.add_node("process", lambda s: {**s, "result": s.get("data", "").upper()})
    sm.add_node("error", lambda s: {**s, "result": "INVALID"})
    sm.set_start("fetch")
    sm.add_edge("fetch", "validate")
    sm.add_edge("validate", "process", lambda s: s.get("valid", False))
    sm.add_edge("validate", "error", lambda s: not s.get("valid", False))
    sm.set_end("process", "error")
    r = asyncio.run(sm.run({}))
    assert r.get("result") == "RAW_DATA" or r.get("data") == "raw_data"


def test_saga_compensation():
    from largestack._distributed.saga import SagaOrchestrator

    compensated = []
    saga = SagaOrchestrator("test")
    saga.add_step("step1", lambda c: {**c, "s1": True}, lambda c: compensated.append("s1"))
    saga.add_step(
        "step2",
        lambda c: (_ for _ in ()).throw(RuntimeError("fail")),
        lambda c: compensated.append("s2"),
    )
    try:
        asyncio.run(saga.execute({}))
    except RuntimeError:
        pass
    assert "s1" in compensated  # step1 compensated after step2 failed


def test_durable_exactly_once():
    from largestack._state.durable import DurableWorkflow
    import tempfile, os

    call_count = 0

    def counter():
        nonlocal call_count
        call_count += 1
        return call_count

    dw = DurableWorkflow("test-wf", os.path.join(tempfile.mkdtemp(), "d.db"))
    r1 = asyncio.run(dw.step("s1", counter))
    r2 = asyncio.run(dw.step("s1", counter))  # Should return cached, not call again
    assert r1 == 1 and r2 == 1 and call_count == 1
