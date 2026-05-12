from pathlib import Path
from largestack import Agent, Orchestrator, TestModel


def test_orchestrator_durable_completed_resume(tmp_path: Path):
    db = tmp_path / "checkpoints.db"
    agent = Agent(name="durable-a")
    orch = Orchestrator(
        name="durable-test",
        strategy="sequential",
        agents=[agent],
        durable=True,
        thread_id="thread-1",
        checkpoint_db_path=str(db),
    )
    with agent.override(model=TestModel("first-output")):
        result = orch.run_sync("run once")
    assert result.output
    assert result.metadata["durable"] is True

    second = Orchestrator(
        name="durable-test",
        strategy="sequential",
        agents=[agent],
        durable=True,
        thread_id="thread-1",
        checkpoint_db_path=str(db),
        resume_completed=True,
    )
    with agent.override(model=TestModel("should-not-be-needed")):
        resumed = second.run_sync("run once")
    assert resumed.metadata["resumed"] is True
    assert resumed.strategy == "sequential"
