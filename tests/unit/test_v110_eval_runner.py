"""v0.11.0: Tests for real eval suite runner."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


# -------------------- run_case --------------------

@pytest.mark.asyncio
async def test_run_case_passes_with_contains():
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "The capital of France is Paris."

    case = {
        "name": "fr_capital",
        "input": "What is the capital of France?",
        "contains": ["Paris"],
    }
    result = await run_case(case, agent_runner=agent)
    assert result.passed is True
    assert result.contains_ok is True
    assert result.answer == "The capital of France is Paris."


@pytest.mark.asyncio
async def test_run_case_fails_when_contains_missing():
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "I don't know."

    case = {
        "name": "should_fail",
        "input": "What is the capital of France?",
        "contains": ["Paris"],
    }
    result = await run_case(case, agent_runner=agent)
    assert result.passed is False
    assert result.contains_ok is False


@pytest.mark.asyncio
async def test_run_case_handles_agent_error():
    from largestack._eval.runner import run_case

    async def broken_agent(input_str: str) -> str:
        raise RuntimeError("agent crashed")

    case = {"name": "broken", "input": "x", "contains": ["x"]}
    result = await run_case(case, agent_runner=broken_agent)
    assert result.passed is False
    assert "agent error" in result.error


@pytest.mark.asyncio
async def test_run_case_with_llm_judge_metrics():
    """End-to-end: agent answers, judge scores faithfulness."""
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "Paris is the capital of France."

    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content='{"score": 9, "reasoning": "verified"}'
    ))

    case = {
        "name": "with_metrics",
        "input": "What is the capital of France?",
        "context": "France's capital city is Paris.",
        "ground_truth": "Paris",
        "metrics": ["faithfulness", "answer_relevance"],
    }
    result = await run_case(
        case, agent_runner=agent, judge_runner=judge, threshold=0.7,
    )
    assert "faithfulness" in result.metric_scores
    assert "answer_relevance" in result.metric_scores
    assert result.metric_scores["faithfulness"] == 0.9
    assert result.passed is True
    assert result.avg_score == 0.9


@pytest.mark.asyncio
async def test_run_case_fails_threshold():
    """Low metric score → fail."""
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "fabricated answer"

    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content='{"score": 3, "reasoning": "fabricated"}'
    ))

    case = {
        "name": "below_threshold",
        "input": "X?",
        "context": "Real answer is Y.",
        "metrics": ["faithfulness"],
    }
    result = await run_case(
        case, agent_runner=agent, judge_runner=judge, threshold=0.7,
    )
    assert result.passed is False
    assert result.avg_score == 0.3


@pytest.mark.asyncio
async def test_run_case_contains_overrides_metric_pass():
    """Even if metrics pass, missing contains → fail."""
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "high quality answer without keyword"

    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(
        content='{"score": 10, "reasoning": "great"}'
    ))

    case = {
        "name": "contains_strict",
        "input": "X?",
        "contains": ["KEYWORD_MUST_APPEAR"],
        "metrics": ["answer_relevance"],
    }
    result = await run_case(
        case, agent_runner=agent, judge_runner=judge,
    )
    # Metrics passed but contains failed → overall fail
    assert result.contains_ok is False
    assert result.passed is False


@pytest.mark.asyncio
async def test_run_case_no_metrics_no_contains_passes():
    """Default to pass if no checks defined."""
    from largestack._eval.runner import run_case

    async def agent(input_str: str) -> str:
        return "anything"

    case = {"name": "loose", "input": "x"}
    result = await run_case(case, agent_runner=agent)
    assert result.passed is True


# -------------------- run_suite --------------------

@pytest.mark.asyncio
async def test_run_suite_loads_and_executes(tmp_path):
    pytest.importorskip("yaml")
    from largestack._eval.runner import run_suite

    suite_yaml = tmp_path / "suite.yaml"
    suite_yaml.write_text("""\
name: my-suite
threshold: 0.7
cases:
  - name: case_pass
    input: foo
    contains: [foo]
  - name: case_fail
    input: bar
    contains: [definitely_not_in_answer]
""")

    async def agent(x: str) -> str:
        return f"echo: {x}"

    result = await run_suite(suite_yaml, agent_runner=agent)
    assert result.name == "my-suite"
    assert len(result.cases) == 2
    assert result.passed_count == 1
    assert result.failed_count == 1
    assert result.pass_rate == 0.5


@pytest.mark.asyncio
async def test_run_suite_missing_file():
    from largestack._eval.runner import run_suite
    async def agent(x): return ""
    with pytest.raises(FileNotFoundError):
        await run_suite("/nonexistent.yaml", agent_runner=agent)


@pytest.mark.asyncio
async def test_run_suite_empty_cases(tmp_path):
    pytest.importorskip("yaml")
    from largestack._eval.runner import run_suite
    suite_yaml = tmp_path / "empty.yaml"
    suite_yaml.write_text("name: empty\ncases: []\n")
    async def agent(x): return "x"
    result = await run_suite(suite_yaml, agent_runner=agent)
    assert len(result.cases) == 0
    assert result.pass_rate == 0.0


# -------------------- SuiteResult formatting --------------------

def test_suite_result_to_dict():
    from largestack._eval.runner import SuiteResult, CaseResult
    suite = SuiteResult(name="t", threshold=0.7)
    suite.cases.append(CaseResult(
        name="c1", input="i", answer="a", passed=True, avg_score=0.9,
    ))
    suite.cases.append(CaseResult(
        name="c2", input="i", answer="a", passed=False, error="oops",
    ))
    suite.duration_seconds = 1.5

    d = suite.to_dict()
    assert d["summary"]["total"] == 2
    assert d["summary"]["passed"] == 1
    assert d["summary"]["errors"] == 1
    assert d["summary"]["pass_rate"] == 0.5
    assert len(d["cases"]) == 2


def test_suite_result_to_junit_xml():
    from largestack._eval.runner import SuiteResult, CaseResult
    suite = SuiteResult(name="t", threshold=0.7)
    suite.cases.append(CaseResult(
        name="passes", input="x", passed=True, duration_seconds=0.1,
    ))
    suite.cases.append(CaseResult(
        name="fails", input="x", passed=False, avg_score=0.3,
    ))
    suite.cases.append(CaseResult(
        name="errors", input="x", error="boom",
    ))

    xml = suite.to_junit_xml()
    assert '<?xml' in xml
    assert '<testsuite' in xml
    assert 'tests="3"' in xml
    assert 'failures="2"' in xml
    assert '<failure' in xml
    assert '<error' in xml


def test_suite_result_pass_rate_zero_cases():
    from largestack._eval.runner import SuiteResult
    suite = SuiteResult(name="empty", threshold=0.7)
    assert suite.pass_rate == 0.0


def test_format_console_report():
    from largestack._eval.runner import (
        SuiteResult, CaseResult, format_console_report,
    )
    suite = SuiteResult(name="my-suite", threshold=0.7)
    suite.cases.append(CaseResult(
        name="c1", input="i", passed=True,
        metric_scores={"faithfulness": 0.9},
    ))
    suite.cases.append(CaseResult(
        name="c2", input="i", passed=False,
        metric_scores={"faithfulness": 0.4},
    ))
    suite.cases.append(CaseResult(
        name="c3", input="i", error="LLM down",
    ))

    out = format_console_report(suite)
    assert "my-suite" in out
    assert "Pass: 1" in out
    assert "Fail: 1" in out
    assert "Errors: 1" in out
    assert "✓" in out
    assert "✗" in out
    assert "💥" in out


# -------------------- Threshold edge cases --------------------

@pytest.mark.asyncio
async def test_run_case_at_threshold_passes():
    from largestack._eval.runner import run_case
    async def agent(x): return "ok"
    judge = MagicMock()
    judge.run = AsyncMock(return_value=MagicMock(content='{"score": 7}'))
    case = {
        "name": "at_threshold",
        "input": "x",
        "metrics": ["answer_relevance"],
    }
    result = await run_case(
        case, agent_runner=agent, judge_runner=judge, threshold=0.7,
    )
    assert result.avg_score == 0.7
    assert result.passed is True
