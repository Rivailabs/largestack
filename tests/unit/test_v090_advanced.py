"""v0.9.0: Tests for checkpointing, RAG eval, citation engine, code interpreter."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- Memory Checkpoint Store --------------------

@pytest.mark.asyncio
async def test_memory_checkpoint_save_and_load():
    from largestack._workflow.checkpoint import MemoryCheckpointStore, Checkpoint
    import time

    store = MemoryCheckpointStore()
    cp = Checkpoint(
        thread_id="t1", checkpoint_id="cp1", node_name="research",
        state={"step": 1}, timestamp=time.time(),
    )
    await store.save(cp)
    loaded = await store.load("t1", "cp1")
    assert loaded is not None
    assert loaded.node_name == "research"
    assert loaded.state["step"] == 1


@pytest.mark.asyncio
async def test_memory_checkpoint_list_in_timestamp_order():
    from largestack._workflow.checkpoint import MemoryCheckpointStore, Checkpoint
    store = MemoryCheckpointStore()
    cp_a = Checkpoint(
        thread_id="t1", checkpoint_id="a", node_name="n1",
        state={}, timestamp=100.0,
    )
    cp_b = Checkpoint(
        thread_id="t1", checkpoint_id="b", node_name="n2",
        state={}, timestamp=200.0,
    )
    cp_c = Checkpoint(
        thread_id="t1", checkpoint_id="c", node_name="n3",
        state={}, timestamp=50.0,
    )
    await store.save(cp_a)
    await store.save(cp_b)
    await store.save(cp_c)
    cps = await store.list_for_thread("t1")
    assert [c.checkpoint_id for c in cps] == ["c", "a", "b"]


@pytest.mark.asyncio
async def test_memory_checkpoint_latest():
    from largestack._workflow.checkpoint import MemoryCheckpointStore, Checkpoint
    store = MemoryCheckpointStore()
    await store.save(Checkpoint(
        thread_id="t1", checkpoint_id="early", node_name="n",
        state={}, timestamp=100.0,
    ))
    await store.save(Checkpoint(
        thread_id="t1", checkpoint_id="late", node_name="n",
        state={}, timestamp=200.0,
    ))
    latest = await store.latest("t1")
    assert latest.checkpoint_id == "late"


@pytest.mark.asyncio
async def test_memory_checkpoint_delete_thread():
    from largestack._workflow.checkpoint import MemoryCheckpointStore, Checkpoint
    store = MemoryCheckpointStore()
    for i in range(3):
        await store.save(Checkpoint(
            thread_id="t1", checkpoint_id=f"cp{i}",
            node_name="n", state={}, timestamp=float(i),
        ))
    n = await store.delete_thread("t1")
    assert n == 3
    assert await store.list_for_thread("t1") == []


@pytest.mark.asyncio
async def test_memory_checkpoint_unknown_returns_none():
    from largestack._workflow.checkpoint import MemoryCheckpointStore
    store = MemoryCheckpointStore()
    assert await store.load("nope", "cp1") is None
    assert await store.latest("nope") is None


@pytest.mark.asyncio
async def test_checkpoint_node_helper():
    from largestack._workflow.checkpoint import (
        MemoryCheckpointStore, checkpoint_node,
    )
    store = MemoryCheckpointStore()
    cp = await checkpoint_node(
        store, thread_id="t1", node_name="research",
        state={"data": "x"},
    )
    assert cp.thread_id == "t1"
    assert cp.checkpoint_id.startswith("cp_")
    assert cp.node_name == "research"

    loaded = await store.load("t1", cp.checkpoint_id)
    assert loaded is not None


# -------------------- Redis Checkpoint Store --------------------

@pytest.mark.asyncio
async def test_redis_checkpoint_handles_missing_redis():
    from largestack._workflow.checkpoint import RedisCheckpointStore, Checkpoint
    import sys
    saved = sys.modules.pop("redis", None)
    saved_async = sys.modules.pop("redis.asyncio", None)
    sys.modules["redis"] = None
    sys.modules["redis.asyncio"] = None
    try:
        store = RedisCheckpointStore()
        cp = Checkpoint(
            thread_id="t", checkpoint_id="x", node_name="n",
            state={}, timestamp=0.0,
        )
        with pytest.raises(ImportError, match="redis"):
            await store.save(cp)
    finally:
        if saved is not None:
            sys.modules["redis"] = saved
        else:
            sys.modules.pop("redis", None)
        if saved_async is not None:
            sys.modules["redis.asyncio"] = saved_async
        else:
            sys.modules.pop("redis.asyncio", None)


# -------------------- Citation Engine --------------------

def test_citation_engine_inserts_citations():
    from largestack._core.citation_sandbox import CitationEngine
    engine = CitationEngine(min_overlap=0.1)
    cited = engine.cite(
        answer="The product launched in June 2024. It supports two modes A and B.",
        documents=[
            {"id": "d1", "content": "The product launched in June 2024 in beta."},
            {"id": "d2", "content": "It supports two modes A and B for users."},
        ],
    )
    assert "[1]" in cited.text_with_citations
    assert "[2]" in cited.text_with_citations


def test_citation_engine_no_match_no_citation():
    from largestack._core.citation_sandbox import CitationEngine
    engine = CitationEngine(min_overlap=0.5)
    cited = engine.cite(
        answer="Some unrelated statement.",
        documents=[{"id": "d", "content": "totally different content here"}],
    )
    assert "[" not in cited.text_with_citations


def test_citation_engine_collects_unique_sources():
    from largestack._core.citation_sandbox import CitationEngine
    engine = CitationEngine(min_overlap=0.1)
    cited = engine.cite(
        answer="Sentence one matching doc one. Sentence two matching doc one again.",
        documents=[
            {"id": "doc_a", "content": "matching one statement here"},
        ],
    )
    # Only one source should appear (deduplicated)
    assert len(cited.sources) == 1


def test_citation_engine_custom_format():
    from largestack._core.citation_sandbox import CitationEngine
    engine = CitationEngine(min_overlap=0.1, citation_format="({n})")
    cited = engine.cite(
        answer="Hello world from this test.",
        documents=[{"id": "d", "content": "Hello world from this test"}],
    )
    assert "(1)" in cited.text_with_citations


# -------------------- RAG Eval --------------------

@pytest.mark.asyncio
async def test_faithfulness_metric():
    from largestack._rag.eval import faithfulness
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content='{"score": 9, "reasoning": "all claims verified"}'
    ))
    result = await faithfulness(
        judge, question="Q?", answer="A.", context="context",
    )
    assert result.metric == "faithfulness"
    assert result.score == 0.9
    assert result.raw_score == 9.0
    assert "verified" in result.reasoning


@pytest.mark.asyncio
async def test_answer_relevance_metric():
    from largestack._rag.eval import answer_relevance
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content='{"score": 8, "reasoning": "addresses question well"}'
    ))
    result = await answer_relevance(judge, question="Q?", answer="A.")
    assert result.score == 0.8


@pytest.mark.asyncio
async def test_context_precision():
    from largestack._rag.eval import context_precision
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content='{"score": 7}'))
    result = await context_precision(
        judge, question="Q?",
        retrieved_chunks=["chunk1", "chunk2"],
    )
    assert result.score == 0.7


@pytest.mark.asyncio
async def test_context_recall():
    from largestack._rag.eval import context_recall
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content='{"score": 6}'))
    result = await context_recall(
        judge, ground_truth="G", context="C",
    )
    assert result.score == 0.6


@pytest.mark.asyncio
async def test_evaluate_runs_all_metrics():
    from largestack._rag.eval import evaluate
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content='{"score": 8}'))
    result = await evaluate(
        judge,
        question="Q", answer="A", context="ctx",
        retrieved_chunks=["c1", "c2"],
        ground_truth="GT",
    )
    assert "faithfulness" in result.metrics
    assert "answer_relevance" in result.metrics
    assert "context_precision" in result.metrics
    assert "context_recall" in result.metrics
    assert result.average_score == 0.8


@pytest.mark.asyncio
async def test_evaluate_skips_optional_metrics():
    """No retrieved_chunks/ground_truth → those metrics not run."""
    from largestack._rag.eval import evaluate
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content='{"score": 9}'))
    result = await evaluate(
        judge, question="Q", answer="A", context="ctx",
    )
    assert "faithfulness" in result.metrics
    assert "context_precision" not in result.metrics
    assert "context_recall" not in result.metrics


@pytest.mark.asyncio
async def test_eval_handles_unparseable_judge_response():
    from largestack._rag.eval import faithfulness
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content="I think this answer is okay, like 7/10."
    ))
    result = await faithfulness(judge, question="Q", answer="A", context="C")
    # Falls back to regex extraction
    assert 0 <= result.score <= 1


@pytest.mark.asyncio
async def test_eval_handles_judge_exception():
    from largestack._rag.eval import faithfulness
    judge = MagicMock()
    judge.run = AsyncMock(side_effect=RuntimeError("LLM failed"))
    result = await faithfulness(judge, question="Q", answer="A", context="C")
    assert result.score == 0.0


# -------------------- Code Interpreter --------------------

@pytest.mark.asyncio
async def test_code_interpreter_runs_simple_code():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter(timeout_seconds=10)
    result = await sandbox.execute("print('hello')\nprint(2 + 2)")
    assert result.success
    assert "hello" in result.stdout
    assert "4" in result.stdout


@pytest.mark.asyncio
async def test_code_interpreter_captures_stderr():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter()
    result = await sandbox.execute(
        "import sys\nprint('to stderr', file=sys.stderr)"
    )
    assert "to stderr" in result.stderr


@pytest.mark.asyncio
async def test_code_interpreter_nonzero_exit():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter()
    result = await sandbox.execute("import sys\nsys.exit(1)")
    assert not result.success
    assert result.returncode == 1


@pytest.mark.asyncio
async def test_code_interpreter_timeout():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter(timeout_seconds=2)
    result = await sandbox.execute("import time\ntime.sleep(10)")
    assert result.timed_out
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_code_interpreter_empty_code_returns_error():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter()
    result = await sandbox.execute("")
    assert "empty" in result.error


@pytest.mark.asyncio
async def test_code_interpreter_module_allowlist_blocks_disallowed():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter(allowed_modules=["math"], timeout_seconds=10)
    result = await sandbox.execute("import socket")
    # Should fail with import restriction
    assert "not in allowlist" in result.stderr or result.returncode != 0


@pytest.mark.asyncio
async def test_code_interpreter_module_allowlist_allows_listed():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter(allowed_modules=["math"], timeout_seconds=10)
    result = await sandbox.execute("import math\nprint(math.pi)")
    assert result.success
    assert "3.14" in result.stdout


@pytest.mark.asyncio
async def test_code_interpreter_truncates_large_output():
    from largestack._core.citation_sandbox import CodeInterpreter
    sandbox = CodeInterpreter(max_output_chars=100, timeout_seconds=10)
    code = "for i in range(10000): print('xxxxx')"
    result = await sandbox.execute(code)
    assert "[truncated]" in result.stdout
