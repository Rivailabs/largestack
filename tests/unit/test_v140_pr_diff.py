"""v0.14.0: Tests for eval PR diff comments."""

from __future__ import annotations

import json

import pytest


def _baseline_report():
    return {
        "summary": {"pass_rate": 0.94, "passed": 47, "total": 50},
        "cases": [
            {"name": "kyc_pan_valid", "passed": True},
            {"name": "kyc_aadhaar_redact", "passed": True},
            {"name": "kyc_gst_lookup", "passed": True},
            {"name": "kyc_cibil_check", "passed": False},
        ],
    }


def _current_report():
    return {
        "summary": {"pass_rate": 0.87, "passed": 42, "total": 48},
        "cases": [
            {"name": "kyc_pan_valid", "passed": True},
            {"name": "kyc_aadhaar_redact", "passed": False},  # regression
            {"name": "kyc_gst_lookup", "passed": True},
            {"name": "kyc_cibil_check", "passed": True},  # improvement
            {"name": "kyc_mca_lookup", "passed": True},  # new
        ],
    }


# -------------------- compute_eval_delta --------------------


def test_compute_delta_finds_regression():
    from largestack._eval.pr_diff import compute_eval_delta

    delta = compute_eval_delta(_baseline_report(), _current_report())
    names = [r.name for r in delta.regressions]
    assert "kyc_aadhaar_redact" in names


def test_compute_delta_finds_improvement():
    from largestack._eval.pr_diff import compute_eval_delta

    delta = compute_eval_delta(_baseline_report(), _current_report())
    names = [i.name for i in delta.improvements]
    assert "kyc_cibil_check" in names


def test_compute_delta_finds_new_case():
    from largestack._eval.pr_diff import compute_eval_delta

    delta = compute_eval_delta(_baseline_report(), _current_report())
    names = [n.name for n in delta.new_cases]
    assert "kyc_mca_lookup" in names


def test_compute_delta_pass_rate_calculation():
    from largestack._eval.pr_diff import compute_eval_delta

    delta = compute_eval_delta(_baseline_report(), _current_report())
    assert abs(delta.pass_rate_delta - (0.87 - 0.94)) < 0.001
    assert delta.is_overall_regression
    assert delta.has_regressions


def test_compute_delta_no_changes_for_identical():
    from largestack._eval.pr_diff import compute_eval_delta

    delta = compute_eval_delta(_baseline_report(), _baseline_report())
    assert not delta.regressions
    assert not delta.improvements
    assert not delta.is_overall_regression


def test_compute_delta_handles_missing_summary():
    """Computes pass rate from cases when no summary present."""
    from largestack._eval.pr_diff import compute_eval_delta

    a = {
        "cases": [
            {"name": "c1", "passed": True},
            {"name": "c2", "passed": False},
        ]
    }
    b = {
        "cases": [
            {"name": "c1", "passed": True},
            {"name": "c2", "passed": True},
        ]
    }
    delta = compute_eval_delta(a, b)
    assert delta.baseline_pass_rate == 0.5
    assert delta.current_pass_rate == 1.0


# -------------------- Markdown rendering --------------------


def test_render_markdown_contains_summary_table():
    from largestack._eval.pr_diff import compute_eval_delta, render_pr_comment_markdown

    delta = compute_eval_delta(_baseline_report(), _current_report())
    md = render_pr_comment_markdown(delta, suite_name="KYC")
    assert "KYC" in md
    assert "Pass rate" in md
    assert "94.0%" in md
    assert "87.0%" in md


def test_render_markdown_lists_regressions():
    from largestack._eval.pr_diff import compute_eval_delta, render_pr_comment_markdown

    delta = compute_eval_delta(_baseline_report(), _current_report())
    md = render_pr_comment_markdown(delta)
    assert "Regressions" in md
    assert "kyc_aadhaar_redact" in md


def test_render_markdown_uses_warning_icon_on_regression():
    from largestack._eval.pr_diff import compute_eval_delta, render_pr_comment_markdown

    delta = compute_eval_delta(_baseline_report(), _current_report())
    md = render_pr_comment_markdown(delta)
    assert "⚠️" in md


def test_render_markdown_stable_when_unchanged():
    from largestack._eval.pr_diff import compute_eval_delta, render_pr_comment_markdown

    delta = compute_eval_delta(_baseline_report(), _baseline_report())
    md = render_pr_comment_markdown(delta)
    assert "stable" in md.lower() or "✅" in md


# -------------------- Slack rendering --------------------


def test_render_slack_message_short_format():
    from largestack._eval.pr_diff import compute_eval_delta, render_slack_message

    delta = compute_eval_delta(_baseline_report(), _current_report())
    msg = render_slack_message(delta, suite_name="KYC")
    assert "KYC" in msg
    assert "Pass rate" in msg
    # Slack messages should be plain text — no markdown tables
    assert "|---|" not in msg


def test_render_slack_truncates_long_regression_lists():
    from largestack._eval.pr_diff import compute_eval_delta, render_slack_message

    # Build a baseline with 20 passing cases, current with all failing
    baseline = {"cases": [{"name": f"c{i}", "passed": True} for i in range(20)]}
    current = {"cases": [{"name": f"c{i}", "passed": False} for i in range(20)]}
    delta = compute_eval_delta(baseline, current)
    msg = render_slack_message(delta)
    assert "more" in msg  # truncation indicator


# -------------------- File I/O --------------------


def test_load_report_missing_file(tmp_path):
    from largestack._eval.pr_diff import load_report

    with pytest.raises(FileNotFoundError):
        load_report(tmp_path / "nope.json")


def test_diff_report_files_e2e(tmp_path):
    from largestack._eval.pr_diff import diff_report_files

    bp = tmp_path / "baseline.json"
    cp = tmp_path / "current.json"
    bp.write_text(json.dumps(_baseline_report()))
    cp.write_text(json.dumps(_current_report()))

    md = diff_report_files(bp, cp, suite_name="KYC", output_format="markdown")
    assert "KYC" in md
    assert "kyc_aadhaar_redact" in md


def test_diff_report_files_unknown_format(tmp_path):
    from largestack._eval.pr_diff import diff_report_files

    bp = tmp_path / "b.json"
    cp = tmp_path / "c.json"
    bp.write_text("{}")
    cp.write_text("{}")
    with pytest.raises(ValueError, match="unknown format"):
        diff_report_files(bp, cp, output_format="xml")
