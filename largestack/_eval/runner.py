"""Real eval suite runner (v0.11.0).

Replaces the v0.9.0 placeholder. Loads YAML eval suite, runs each case
through an agent, applies LLM-judge metrics, and produces a JUnit-style
report with pass/fail counts. Closes the gap with Promptfoo / DeepEval.

YAML suite format::

    name: my-eval-suite
    judge: openai/gpt-4o-mini
    threshold: 0.7  # min average score per case
    cases:
      - name: case_1
        input: What is the capital of France?
        ground_truth: Paris
        contains: ["Paris"]    # cheap substring check
      - name: case_2
        input: Summarize the document
        context: |
          The document discusses LARGESTACK framework features...
        ground_truth: LARGESTACK is an Indian-fintech-focused agent framework
        metrics: [faithfulness, answer_relevance]

Each case produces:
- ``contains_ok``: substring(s) present in answer (boolean, optional)
- ``faithfulness`` (if context provided)
- ``answer_relevance``
- ``context_recall`` (if ground_truth + context)

A case passes if it meets all defined ``contains`` AND has avg metric
score ≥ threshold.
"""
from __future__ import annotations
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("largestack.eval_runner")


@dataclass
class CaseResult:
    """Result of one eval case."""
    name: str
    input: str
    answer: str = ""
    contains_ok: bool | None = None
    metric_scores: dict[str, float] = field(default_factory=dict)
    avg_score: float = 0.0
    passed: bool = False
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class SuiteResult:
    """Result of running the entire eval suite."""
    name: str
    cases: list[CaseResult] = field(default_factory=list)
    threshold: float = 0.7
    duration_seconds: float = 0.0

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.cases if not c.passed and not c.error)

    @property
    def error_count(self) -> int:
        return sum(1 for c in self.cases if c.error)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return self.passed_count / len(self.cases)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "threshold": self.threshold,
            "summary": {
                "total": len(self.cases),
                "passed": self.passed_count,
                "failed": self.failed_count,
                "errors": self.error_count,
                "pass_rate": round(self.pass_rate, 3),
                "duration_seconds": round(self.duration_seconds, 2),
            },
            "cases": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "avg_score": round(c.avg_score, 3),
                    "metric_scores": {
                        k: round(v, 3) for k, v in c.metric_scores.items()
                    },
                    "contains_ok": c.contains_ok,
                    "error": c.error,
                    "duration_seconds": round(c.duration_seconds, 3),
                }
                for c in self.cases
            ],
        }

    def to_junit_xml(self) -> str:
        """Produce a JUnit-style XML report for CI integration."""
        from xml.sax.saxutils import escape

        total = len(self.cases)
        failures = self.failed_count + self.error_count

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            f'<testsuite name="{escape(self.name)}" tests="{total}" '
            f'failures="{failures}" time="{self.duration_seconds:.2f}">',
        ]
        for c in self.cases:
            lines.append(
                f'  <testcase name="{escape(c.name)}" '
                f'time="{c.duration_seconds:.3f}">'
            )
            if c.error:
                lines.append(
                    f'    <error message="{escape(c.error[:200])}"/>'
                )
            elif not c.passed:
                detail = (
                    f"avg_score={c.avg_score:.2f} threshold={self.threshold} "
                    f"metrics={c.metric_scores} contains_ok={c.contains_ok}"
                )
                lines.append(
                    f'    <failure message="{escape(detail[:500])}"/>'
                )
            lines.append('  </testcase>')
        lines.append('</testsuite>')
        return "\n".join(lines)


# -------------------- Runner --------------------

async def run_case(
    case: dict,
    *,
    agent_runner: Callable[[str], "Awaitable[str]"],
    judge_runner=None,
    threshold: float = 0.7,
) -> CaseResult:
    """Run a single eval case.

    Args:
        case: dict with at least ``name`` and ``input``.
        agent_runner: async callable that takes the input string,
            returns the agent's answer (string).
        judge_runner: optional LARGESTACK Agent for LLM-judge metrics. If
            None, only ``contains`` checks are run.
        threshold: minimum avg metric score for case to pass.
    """
    start = time.time()
    name = case.get("name", "unnamed_case")
    input_text = case.get("input", "")
    ground_truth = case.get("ground_truth", "")
    context = case.get("context", "")
    contains = case.get("contains", [])
    metric_names = case.get("metrics", [])

    if not isinstance(contains, list):
        contains = [contains] if contains else []

    result = CaseResult(name=name, input=input_text)

    # 1) Run the agent
    try:
        answer = await agent_runner(input_text)
        result.answer = str(answer)
    except Exception as e:
        result.error = f"agent error: {e}"
        result.duration_seconds = time.time() - start
        return result

    # 2) Check `contains` (substring assertions)
    if contains:
        all_present = all(
            sub.lower() in result.answer.lower() for sub in contains
        )
        result.contains_ok = all_present

    # 3) Run LLM-judge metrics if requested
    if metric_names and judge_runner is not None:
        try:
            from largestack._rag.eval import (
                faithfulness, answer_relevance,
                context_precision, context_recall,
            )
        except ImportError as e:
            result.error = f"eval metrics unavailable: {e}"
            result.duration_seconds = time.time() - start
            return result

        try:
            for metric_name in metric_names:
                if metric_name == "faithfulness" and context:
                    m = await faithfulness(
                        judge_runner,
                        question=input_text,
                        answer=result.answer,
                        context=context,
                    )
                    result.metric_scores["faithfulness"] = m.score
                elif metric_name == "answer_relevance":
                    m = await answer_relevance(
                        judge_runner,
                        question=input_text,
                        answer=result.answer,
                    )
                    result.metric_scores["answer_relevance"] = m.score
                elif metric_name == "context_recall" and ground_truth and context:
                    m = await context_recall(
                        judge_runner,
                        ground_truth=ground_truth,
                        context=context,
                    )
                    result.metric_scores["context_recall"] = m.score
                elif metric_name == "context_precision" and case.get("retrieved_chunks"):
                    m = await context_precision(
                        judge_runner,
                        question=input_text,
                        retrieved_chunks=case["retrieved_chunks"],
                    )
                    result.metric_scores["context_precision"] = m.score
        except Exception as e:
            result.error = f"judge error: {e}"
            result.duration_seconds = time.time() - start
            return result

    # 4) Compute pass/fail
    if result.metric_scores:
        result.avg_score = (
            sum(result.metric_scores.values()) / len(result.metric_scores)
        )
        meets_threshold = result.avg_score >= threshold
    else:
        # No metrics — fall back to contains check
        meets_threshold = True

    if result.contains_ok is False:
        result.passed = False
    else:
        result.passed = meets_threshold

    result.duration_seconds = time.time() - start
    return result


async def run_suite(
    suite_yaml_path: str | Path,
    *,
    agent_runner: Callable[[str], "Awaitable[str]"],
    judge_runner=None,
) -> SuiteResult:
    """Load and execute a YAML eval suite.

    Args:
        suite_yaml_path: path to the YAML file.
        agent_runner: async callable(input) → answer string.
        judge_runner: optional LARGESTACK agent for LLM-judge metrics.
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("pyyaml required: pip install pyyaml") from e

    suite_path = Path(suite_yaml_path)
    if not suite_path.exists():
        raise FileNotFoundError(f"eval suite not found: {suite_path}")

    with open(suite_path) as f:
        data = yaml.safe_load(f) or {}

    name = data.get("name", suite_path.stem)
    threshold = float(data.get("threshold", 0.7))
    cases = data.get("cases", []) or []

    suite_start = time.time()
    suite_result = SuiteResult(name=name, threshold=threshold)

    for case in cases:
        if not isinstance(case, dict):
            log.warning(f"skipping non-dict case: {case}")
            continue
        cr = await run_case(
            case,
            agent_runner=agent_runner,
            judge_runner=judge_runner,
            threshold=threshold,
        )
        suite_result.cases.append(cr)

    suite_result.duration_seconds = time.time() - suite_start
    return suite_result


# -------------------- Pretty-print helpers --------------------

def format_console_report(suite: SuiteResult) -> str:
    """Format a human-readable summary for console output."""
    lines = []
    lines.append(f"Eval Suite: {suite.name}")
    lines.append("=" * 60)
    lines.append(
        f"Threshold: {suite.threshold:.2f}  |  "
        f"Total: {len(suite.cases)}  |  "
        f"Pass: {suite.passed_count}  |  "
        f"Fail: {suite.failed_count}  |  "
        f"Errors: {suite.error_count}"
    )
    lines.append(f"Pass rate: {suite.pass_rate:.1%}")
    lines.append(f"Duration: {suite.duration_seconds:.2f}s")
    lines.append("-" * 60)
    for c in suite.cases:
        if c.error:
            mark = "💥"
        elif c.passed:
            mark = "✓"
        else:
            mark = "✗"
        line = f"  {mark}  {c.name}"
        if c.metric_scores:
            metrics = ", ".join(
                f"{k}={v:.2f}" for k, v in c.metric_scores.items()
            )
            line += f"  [{metrics}]"
        if c.error:
            line += f"  ERROR: {c.error[:80]}"
        lines.append(line)
    return "\n".join(lines)
