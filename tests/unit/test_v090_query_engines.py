"""v0.9.0: Tests for SubQuestionQueryEngine + RouterQueryEngine."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- SubQuestionQueryEngine --------------------


@pytest.mark.asyncio
async def test_sub_question_decomposes_and_synthesizes():
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(
        return_value=MagicMock(content='["What is X?", "What is Y?", "How do they compare?"]')
    )

    sub_engine = AsyncMock(
        side_effect=[
            "X is a tool",
            "Y is a framework",
            "X is simpler than Y",
        ]
    )

    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="Final synthesis."))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=sub_engine,
        synthesizer_agent=synth,
    )
    result = await engine.query("Compare X and Y")

    assert result.final_answer == "Final synthesis."
    assert len(result.sub_questions) == 3
    assert all(sq.answer for sq in result.sub_questions)


@pytest.mark.asyncio
async def test_sub_question_handles_decompose_failure():
    """If decomposition fails, treat as single question."""
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(return_value=MagicMock(content="not valid JSON"))

    sub_engine = AsyncMock(return_value="single answer")
    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="just one"))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=sub_engine,
        synthesizer_agent=synth,
    )
    result = await engine.query("simple question")
    assert len(result.sub_questions) == 1


@pytest.mark.asyncio
async def test_sub_question_strips_code_fences():
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(return_value=MagicMock(content='```json\n["one", "two"]\n```'))
    sub_engine = AsyncMock(return_value="ans")
    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="final"))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=sub_engine,
        synthesizer_agent=synth,
    )
    result = await engine.query("q")
    assert len(result.sub_questions) == 2


@pytest.mark.asyncio
async def test_sub_question_caps_at_max():
    """Decomposer can't suggest more than max_sub_questions."""
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(
        return_value=MagicMock(content='["q1", "q2", "q3", "q4", "q5", "q6", "q7"]')
    )
    sub_engine = AsyncMock(return_value="x")
    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="ok"))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=sub_engine,
        synthesizer_agent=synth,
        max_sub_questions=3,
    )
    result = await engine.query("q")
    assert len(result.sub_questions) == 3


@pytest.mark.asyncio
async def test_sub_question_handles_sub_engine_failure():
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(return_value=MagicMock(content='["good_q", "bad_q"]'))
    # First succeeds, second fails
    sub_engine = AsyncMock(side_effect=["good answer", RuntimeError("fail")])
    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="partial"))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=sub_engine,
        synthesizer_agent=synth,
    )
    result = await engine.query("q")
    assert any(sq.error for sq in result.sub_questions)
    assert any(sq.answer for sq in result.sub_questions)


@pytest.mark.asyncio
async def test_sub_question_runs_concurrently():
    """Sub-questions should be answered in parallel."""
    from largestack._rag.query_engines import SubQuestionQueryEngine

    decomposer = MagicMock()
    decomposer.run = AsyncMock(return_value=MagicMock(content='["q1", "q2", "q3"]'))

    async def slow_sub(q):
        await asyncio.sleep(0.05)
        return f"answer to {q}"

    synth = MagicMock()
    synth.run = AsyncMock(return_value=MagicMock(content="ok"))

    engine = SubQuestionQueryEngine(
        decomposer_agent=decomposer,
        sub_engine=slow_sub,
        synthesizer_agent=synth,
        max_concurrent=3,
    )
    import time

    start = time.time()
    await engine.query("q")
    elapsed = time.time() - start
    # 3 parallel 0.05s calls should be ~0.05s, not 0.15s
    assert elapsed < 0.12


# -------------------- RouterQueryEngine --------------------


@pytest.mark.asyncio
async def test_router_routes_to_correct_engine():
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(return_value=MagicMock(content="sql_engine"))

    sql_eng = AsyncMock(return_value="SQL result")
    vec_eng = AsyncMock(return_value="vector result")

    rq = RouterQueryEngine(
        router_agent=router,
        engines={"sql_engine": sql_eng, "vector_engine": vec_eng},
        descriptions={
            "sql_engine": "for structured numeric queries",
            "vector_engine": "for semantic doc search",
        },
    )
    result = await rq.query("how many sales last quarter?")
    assert result.chosen_engine == "sql_engine"
    assert result.answer == "SQL result"
    sql_eng.assert_awaited_once()
    vec_eng.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_falls_back_to_default():
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(return_value=MagicMock(content="DEFAULT"))

    eng_a = AsyncMock(return_value="a result")
    eng_b = AsyncMock(return_value="b result")

    rq = RouterQueryEngine(
        router_agent=router,
        engines={"a": eng_a, "b": eng_b},
        default_engine="b",
    )
    result = await rq.query("q")
    assert result.chosen_engine == "b"


@pytest.mark.asyncio
async def test_router_falls_back_on_unknown_engine():
    """If router picks an engine name we don't know, fall back."""
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(return_value=MagicMock(content="hallucinated_engine"))

    a = AsyncMock(return_value="a")
    b = AsyncMock(return_value="b")

    rq = RouterQueryEngine(
        router_agent=router,
        engines={"a": a, "b": b},
        default_engine="a",
    )
    result = await rq.query("q")
    assert result.chosen_engine == "a"


@pytest.mark.asyncio
async def test_router_handles_router_exception():
    """If router agent fails, use default."""
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(side_effect=RuntimeError("router dead"))

    a = AsyncMock(return_value="a-ans")

    rq = RouterQueryEngine(
        router_agent=router,
        engines={"a": a},
    )
    result = await rq.query("q")
    assert result.chosen_engine == "a"
    assert result.answer == "a-ans"


@pytest.mark.asyncio
async def test_router_handles_engine_exception():
    """Engine raising still gives a router result with error info."""
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(return_value=MagicMock(content="broken"))

    broken = AsyncMock(side_effect=RuntimeError("engine broken"))

    rq = RouterQueryEngine(
        router_agent=router,
        engines={"broken": broken},
    )
    result = await rq.query("q")
    assert "broken" in result.answer.lower()


def test_router_validates_empty_engines():
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    with pytest.raises(ValueError, match="empty"):
        RouterQueryEngine(router_agent=router, engines={})


def test_router_validates_default_engine_in_set():
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    a = AsyncMock()
    with pytest.raises(ValueError):
        RouterQueryEngine(
            router_agent=router,
            engines={"a": a},
            default_engine="missing",
        )


@pytest.mark.asyncio
async def test_router_strips_punctuation_from_choice():
    """Router output 'sql_engine.' should still resolve to 'sql_engine'."""
    from largestack._rag.query_engines import RouterQueryEngine

    router = MagicMock()
    router.run = AsyncMock(return_value=MagicMock(content="sql_engine."))

    eng = AsyncMock(return_value="ok")
    rq = RouterQueryEngine(
        router_agent=router,
        engines={"sql_engine": eng},
    )
    result = await rq.query("q")
    assert result.chosen_engine == "sql_engine"
