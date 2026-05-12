"""Tests for enhanced sequential and parallel orchestration."""
import asyncio, sys; sys.path.insert(0, ".")

class MockAgent:
    def __init__(self, name, response=None, fail=False):
        self.name = name
        self.response = response or f"output from {name}"
        self.fail = fail
    async def run(self, task, **kw):
        from largestack.types import AgentResult
        if self.fail:
            raise RuntimeError(f"{self.name} intentional failure")
        return AgentResult(
            agent_name=self.name, content=self.response,
            total_cost=0.01, total_tokens=100, turns=1,
            tool_calls_made=[], trace_id=f"mock-{self.name}"
        )

def test_sequential_basic():
    from largestack._orchestrate.sequential import SequentialPipeline
    pipe = SequentialPipeline(agents=[MockAgent("a", "A"), MockAgent("b", "B"), MockAgent("c", "C")])
    result = asyncio.run(pipe.run("start"))
    # Last stage output wins
    assert result.content == "C"
    assert result.total_cost == 0.03  # 3 stages × 0.01

def test_sequential_history_tracked():
    from largestack._orchestrate.sequential import SequentialPipeline
    pipe = SequentialPipeline(agents=[MockAgent("a"), MockAgent("b")])
    asyncio.run(pipe.run("start"))
    hist = pipe.history
    assert len(hist) == 2
    assert hist[0]["status"] == "completed"
    assert hist[1]["agent"] == "b"

def test_sequential_skip_on_error():
    from largestack._orchestrate.sequential import SequentialPipeline
    pipe = SequentialPipeline(
        agents=[MockAgent("a"), MockAgent("b", fail=True), MockAgent("c")],
        on_error="skip",
    )
    result = asyncio.run(pipe.run("start"))
    # Stage b skipped, c ran (receives a's output as input)
    assert result is not None
    hist = pipe.history
    assert hist[1]["status"] == "skipped"
    assert hist[2]["status"] == "completed"

def test_sequential_fail_on_error():
    from largestack._orchestrate.sequential import SequentialPipeline
    from largestack.errors import LargestackError
    pipe = SequentialPipeline(
        agents=[MockAgent("a"), MockAgent("b", fail=True), MockAgent("c")],
        on_error="fail",
    )
    try:
        asyncio.run(pipe.run("start"))
        assert False, "Should have raised"
    except LargestackError:
        pass

def test_sequential_empty_agents():
    from largestack._orchestrate.sequential import SequentialPipeline
    try:
        SequentialPipeline(agents=[])
        assert False
    except ValueError:
        pass

def test_sequential_bad_on_error():
    from largestack._orchestrate.sequential import SequentialPipeline
    try:
        SequentialPipeline(agents=[MockAgent("a")], on_error="invalid")
        assert False
    except ValueError:
        pass

def test_sequential_accumulate_context():
    from largestack._orchestrate.sequential import SequentialPipeline
    # When accumulating, each stage sees all previous outputs
    captured = []
    class CaptureAgent:
        def __init__(self, name): self.name = name
        async def run(self, task, **kw):
            from largestack.types import AgentResult
            captured.append(task)
            return AgentResult(agent_name=self.name, content=f"{self.name}_out", total_cost=0.01)
    
    pipe = SequentialPipeline(
        agents=[CaptureAgent("a"), CaptureAgent("b"), CaptureAgent("c")],
        accumulate_context=True,
    )
    asyncio.run(pipe.run("original"))
    # Stage 1: just "original"
    # Stage 2: "Stage 1 ... original"
    # Stage 3: "Stage 1 ... Stage 2 ... original"
    assert "original" in captured[0]
    assert "a_out" in captured[1]
    assert "b_out" in captured[2]

def test_parallel_concat():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(agents=[MockAgent("a", "Alpha"), MockAgent("b", "Beta")])
    result = asyncio.run(fan.run("q"))
    assert "Alpha" in result.content
    assert "Beta" in result.content

def test_parallel_best():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(
        agents=[MockAgent("short", "short"), MockAgent("long", "a much longer answer")],
        combiner="best",
    )
    result = asyncio.run(fan.run("q"))
    assert result.content == "a much longer answer"

def test_parallel_vote():
    from largestack._orchestrate.parallel import ParallelFanOut
    # Two agents say "spam", one says "ham" → spam wins
    fan = ParallelFanOut(
        agents=[MockAgent("a", "spam"), MockAgent("b", "spam"), MockAgent("c", "ham")],
        combiner="vote",
    )
    result = asyncio.run(fan.run("classify"))
    assert result.content == "spam"

def test_parallel_first():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(
        agents=[MockAgent("fast", "first result"), MockAgent("slow", "slow result")],
        combiner="first",
    )
    result = asyncio.run(fan.run("q"))
    # Should return one of them (no guaranteed order, but result should be valid)
    assert result.content in ("first result", "slow result")

def test_parallel_skip_errors():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(
        agents=[MockAgent("a", "ok"), MockAgent("bad", fail=True), MockAgent("c", "good")],
        on_error="skip",
    )
    result = asyncio.run(fan.run("q"))
    # Only ok + good included
    assert "ok" in result.content
    assert "good" in result.content

def test_parallel_fail_aborts():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(
        agents=[MockAgent("a"), MockAgent("bad", fail=True)],
        on_error="fail",
    )
    try:
        asyncio.run(fan.run("q"))
        assert False, "Should have raised"
    except RuntimeError:
        pass

def test_parallel_partial_includes_errors():
    from largestack._orchestrate.parallel import ParallelFanOut
    fan = ParallelFanOut(
        agents=[MockAgent("a", "ok"), MockAgent("bad", fail=True)],
        on_error="partial",
    )
    result = asyncio.run(fan.run("q"))
    assert "ok" in result.content
    assert "Errors" in result.content  # Errors section included

def test_parallel_custom_combiner():
    from largestack._orchestrate.parallel import ParallelFanOut
    def custom(results):
        return f"CUSTOM: {len(results)} results"
    
    fan = ParallelFanOut(
        agents=[MockAgent("a"), MockAgent("b")],
        combiner="custom",
        custom_combiner=custom,
    )
    result = asyncio.run(fan.run("q"))
    assert "CUSTOM: 2 results" in result.content

def test_parallel_bad_combiner():
    from largestack._orchestrate.parallel import ParallelFanOut
    try:
        ParallelFanOut(agents=[MockAgent("a")], combiner="nonsense")
        assert False
    except ValueError:
        pass

def test_parallel_empty_agents():
    from largestack._orchestrate.parallel import ParallelFanOut
    try:
        ParallelFanOut(agents=[])
        assert False
    except ValueError:
        pass
