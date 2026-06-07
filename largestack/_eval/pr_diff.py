"""Eval PR diff comments (v0.14.0).

Closes Tier A #9. Generates a GitHub-flavored Markdown diff between
two eval reports for posting in PR comments / Slack messages.

Use case: every PR runs ``largestack eval-block`` against a regression
suite. The CI step compares the new report to the main-branch baseline
and posts a comment::

    | Suite | main | this PR | Δ |
    |---|--:|--:|--:|
    | KYC verification | 94.2% | 87.1% | 🔻 -7.1% |
    | Aadhaar redaction | 100% | 100% | — |

Used by the ``--baseline`` and ``--pr-comment`` flags on
``eval-block``.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CaseDelta:
    """Per-case change between baseline and current."""

    name: str
    baseline_passed: bool | None  # None = case didn't exist in baseline
    current_passed: bool | None  # None = case removed
    is_regression: bool
    is_improvement: bool
    is_new: bool
    is_removed: bool


@dataclass
class EvalDelta:
    """Overall change between two eval reports."""

    baseline_pass_rate: float
    current_pass_rate: float
    baseline_total: int
    current_total: int
    regressions: list[CaseDelta] = field(default_factory=list)
    improvements: list[CaseDelta] = field(default_factory=list)
    new_cases: list[CaseDelta] = field(default_factory=list)
    removed_cases: list[CaseDelta] = field(default_factory=list)
    unchanged_passing: int = 0
    unchanged_failing: int = 0

    @property
    def pass_rate_delta(self) -> float:
        return self.current_pass_rate - self.baseline_pass_rate

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    @property
    def is_overall_regression(self) -> bool:
        return self.pass_rate_delta < -0.001  # 0.1%


# -------------------- Report parsing --------------------


def _extract_case_results(report: dict[str, Any]) -> dict[str, bool]:
    """Pull ``{case_name: passed_bool}`` from any report shape."""
    results: dict[str, bool] = {}

    # Try common shapes
    if "cases" in report and isinstance(report["cases"], list):
        for c in report["cases"]:
            if isinstance(c, dict):
                name = c.get("name", "")
                passed = c.get("passed")
                if passed is None:
                    passed = c.get("pass")
                if passed is None and "summary" in c:
                    s = c["summary"]
                    if isinstance(s, dict):
                        passed = s.get("passed")
                if name and passed is not None:
                    results[name] = bool(passed)

    # results-by-name shape
    if not results and "results" in report:
        r = report["results"]
        if isinstance(r, dict):
            for name, val in r.items():
                if isinstance(val, dict):
                    p = val.get("passed", val.get("pass"))
                    if p is not None:
                        results[name] = bool(p)
                elif isinstance(val, bool):
                    results[name] = val

    return results


def _extract_summary(report: dict[str, Any]) -> tuple[float, int, int]:
    """Pull ``(pass_rate, passed_count, total_count)``."""
    summary = report.get("summary", {})
    if isinstance(summary, dict):
        pr = summary.get("pass_rate")
        passed = summary.get("passed", 0)
        total = summary.get("total", 0)
        if pr is not None:
            return float(pr), int(passed), int(total)

    # Top-level fields
    pr = report.get("pass_rate")
    passed = report.get("passed", 0)
    total = report.get("total", 0)
    if pr is not None:
        return float(pr), int(passed), int(total)

    # Compute from cases
    case_results = _extract_case_results(report)
    if case_results:
        total = len(case_results)
        passed = sum(1 for v in case_results.values() if v)
        return (passed / total if total else 0.0), passed, total

    return 0.0, 0, 0


# -------------------- Diff computation --------------------


def compute_eval_delta(
    baseline_report: dict[str, Any],
    current_report: dict[str, Any],
) -> EvalDelta:
    """Compute the delta between two eval reports."""
    baseline_cases = _extract_case_results(baseline_report)
    current_cases = _extract_case_results(current_report)

    baseline_pr, _, baseline_total = _extract_summary(baseline_report)
    current_pr, _, current_total = _extract_summary(current_report)

    delta = EvalDelta(
        baseline_pass_rate=baseline_pr,
        current_pass_rate=current_pr,
        baseline_total=baseline_total,
        current_total=current_total,
    )

    all_names = set(baseline_cases.keys()) | set(current_cases.keys())
    for name in sorted(all_names):
        b = baseline_cases.get(name)
        c = current_cases.get(name)
        cd = CaseDelta(
            name=name,
            baseline_passed=b,
            current_passed=c,
            is_regression=(b is True and c is False),
            is_improvement=(b is False and c is True),
            is_new=(b is None and c is not None),
            is_removed=(b is not None and c is None),
        )
        if cd.is_regression:
            delta.regressions.append(cd)
        elif cd.is_improvement:
            delta.improvements.append(cd)
        elif cd.is_new:
            delta.new_cases.append(cd)
        elif cd.is_removed:
            delta.removed_cases.append(cd)
        elif b is True and c is True:
            delta.unchanged_passing += 1
        elif b is False and c is False:
            delta.unchanged_failing += 1

    return delta


# -------------------- Markdown rendering --------------------


def render_pr_comment_markdown(
    delta: EvalDelta,
    *,
    suite_name: str = "Eval suite",
    baseline_label: str = "main",
    current_label: str = "this PR",
    show_unchanged: bool = False,
) -> str:
    """Render the diff as a GitHub-flavored Markdown comment."""
    lines: list[str] = []

    if delta.is_overall_regression:
        header = f"### ⚠️ Eval regression in `{suite_name}`"
    elif delta.has_regressions:
        header = f"### ⚠️ Some cases regressed in `{suite_name}`"
    elif delta.pass_rate_delta > 0.001:
        header = f"### ✅ Eval improvement in `{suite_name}`"
    else:
        header = f"### ✅ Eval stable in `{suite_name}`"
    lines.append(header)
    lines.append("")

    # Summary table
    lines.append(f"| Metric | {baseline_label} | {current_label} | Δ |")
    lines.append("|---|--:|--:|--:|")
    delta_pct = delta.pass_rate_delta * 100
    delta_str = (
        f"🔻 {delta_pct:.1f}%"
        if delta_pct < -0.05
        else f"🔺 +{delta_pct:.1f}%"
        if delta_pct > 0.05
        else "—"
    )
    lines.append(
        f"| Pass rate | {delta.baseline_pass_rate * 100:.1f}% "
        f"| {delta.current_pass_rate * 100:.1f}% | {delta_str} |"
    )
    lines.append(
        f"| Total cases | {delta.baseline_total} | {delta.current_total} "
        f"| {delta.current_total - delta.baseline_total:+d} |"
    )
    lines.append("")

    if delta.regressions:
        lines.append(f"#### 🔴 Regressions ({len(delta.regressions)})")
        for r in delta.regressions:
            lines.append(f"- `{r.name}` — was passing on `{baseline_label}`")
        lines.append("")

    if delta.improvements:
        lines.append(f"#### 🟢 Improvements ({len(delta.improvements)})")
        for i in delta.improvements:
            lines.append(f"- `{i.name}` — now passing")
        lines.append("")

    if delta.new_cases:
        lines.append(f"#### ➕ New cases ({len(delta.new_cases)})")
        for n in delta.new_cases:
            sym = "✓" if n.current_passed else "✗"
            lines.append(f"- {sym} `{n.name}`")
        lines.append("")

    if delta.removed_cases:
        lines.append(f"#### ➖ Removed cases ({len(delta.removed_cases)})")
        for r in delta.removed_cases:
            lines.append(f"- `{r.name}`")
        lines.append("")

    if show_unchanged:
        lines.append(
            f"_{delta.unchanged_passing} cases unchanged passing, "
            f"{delta.unchanged_failing} unchanged failing_"
        )
        lines.append("")

    return "\n".join(lines)


def render_slack_message(
    delta: EvalDelta,
    *,
    suite_name: str = "Eval suite",
    baseline_label: str = "main",
    current_label: str = "this PR",
) -> str:
    """Render the diff as a plain-text Slack message (no markdown tables)."""
    lines: list[str] = []
    icon = "⚠️" if delta.is_overall_regression else "✅"
    lines.append(f"{icon} *Eval result — {suite_name}*")
    delta_pct = delta.pass_rate_delta * 100
    sign = "+" if delta_pct >= 0 else ""
    lines.append(
        f"Pass rate: {delta.baseline_pass_rate * 100:.1f}% "
        f"→ {delta.current_pass_rate * 100:.1f}% "
        f"({sign}{delta_pct:.1f}%)"
    )
    if delta.regressions:
        lines.append(
            f"🔴 {len(delta.regressions)} regression{'' if len(delta.regressions) == 1 else 's'}"
        )
        for r in delta.regressions[:5]:
            lines.append(f"  • {r.name}")
        if len(delta.regressions) > 5:
            lines.append(f"  • ...and {len(delta.regressions) - 5} more")
    if delta.improvements:
        lines.append(f"🟢 {len(delta.improvements)} improvement(s)")

    return "\n".join(lines)


# -------------------- Convenience loaders --------------------


def load_report(path: str | Path) -> dict[str, Any]:
    """Load a JSON eval report from disk."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"report not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def diff_report_files(
    baseline_path: str | Path,
    current_path: str | Path,
    *,
    suite_name: str = "Eval suite",
    output_format: str = "markdown",
) -> str:
    """Compute and render the diff between two report files on disk."""
    baseline = load_report(baseline_path)
    current = load_report(current_path)
    delta = compute_eval_delta(baseline, current)
    if output_format == "markdown":
        return render_pr_comment_markdown(delta, suite_name=suite_name)
    if output_format == "slack":
        return render_slack_message(delta, suite_name=suite_name)
    raise ValueError(f"unknown format: {output_format}")


__all__ = [
    "CaseDelta",
    "EvalDelta",
    "compute_eval_delta",
    "render_pr_comment_markdown",
    "render_slack_message",
    "load_report",
    "diff_report_files",
]
