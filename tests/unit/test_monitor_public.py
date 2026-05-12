from pathlib import Path
from largestack import Monitor
from largestack._observe.traces_db import log_trace


def test_monitor_trace_feedback_and_summary(tmp_path: Path):
    db = tmp_path / "traces.db"
    log_trace(
        trace_id="t1",
        agent="agent-a",
        task="hello",
        model="test-model",
        output="ok",
        duration_ms=12.5,
        cost=0.01,
        tokens=42,
        db_path=str(db),
    )
    monitor = Monitor(str(db))
    traces = monitor.list_traces()
    assert traces and traces[0]["trace_id"] == "t1"
    assert monitor.get_trace("t1")["output"] == "ok"
    rec = monitor.record_feedback("t1", rating=5, label="accepted", metadata={"case": "unit"})
    assert rec.rating == 5
    assert monitor.list_feedback("t1")[0]["metadata"]["case"] == "unit"
    ev = monitor.evaluate_trace("t1")
    assert ev["status"] == "ok"
    assert ev["average_rating"] == 5
    summary = monitor.summary()
    assert summary["traces"] == 1
    assert summary["total_cost"] == 0.01
