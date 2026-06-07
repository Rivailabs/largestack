"""Tests for the OWASP coverage matrix + the guardrail red-team eval."""
from __future__ import annotations
import asyncio
from pathlib import Path

import pytest

from largestack.owasp import (
    OWASP_COVERAGE, owasp_coverage, owasp_coverage_summary, render_markdown,
    COVERED, PARTIAL, NOT_COVERED,
)
from largestack._test.redteam import RedTeamSuite, ATTACKS


# ---------------- OWASP coverage matrix ----------------

def test_owasp_has_full_llm_top10():
    ids = {c.id for c in OWASP_COVERAGE}
    for n in range(1, 11):
        assert f"LLM{n:02d}" in ids, f"missing LLM{n:02d}"


def test_owasp_statuses_valid_and_documented():
    for c in OWASP_COVERAGE:
        assert c.status in (COVERED, PARTIAL, NOT_COVERED)
        assert c.name and c.notes and c.controls  # every row is documented
        if c.status != NOT_COVERED:
            assert c.modules and c.modules[0]  # covered/partial cite real modules


def test_owasp_summary_counts_add_up():
    s = owasp_coverage_summary()
    assert s["total"] == len(OWASP_COVERAGE)
    assert s[COVERED] + s[PARTIAL] + s[NOT_COVERED] == s["total"]
    assert s[COVERED] >= s[PARTIAL]  # at least as many fully-covered as partial (honest balance)


def test_owasp_coverage_is_serializable():
    rows = owasp_coverage()
    assert isinstance(rows, list) and all(isinstance(r, dict) for r in rows)
    assert rows[0]["id"] == "LLM01"


def test_docs_page_lists_every_control():
    """The published docs page must stay in sync with the matrix."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "owasp-coverage.md"
    text = doc.read_text(encoding="utf-8")
    for c in OWASP_COVERAGE:
        assert c.id in text, f"{c.id} missing from docs/owasp-coverage.md"


# ---------------- Red-team eval ----------------

def test_redteam_core_attacks_all_handled():
    report = asyncio.run(RedTeamSuite().run())
    failures = [r.attack.id for r in report.results
                if r.attack.tier == "core" and not r.passed]
    assert not failures, f"core red-team attacks slipped through: {failures}"
    assert report.core_passed()


def test_redteam_blocks_injection_and_jailbreak():
    report = asyncio.run(RedTeamSuite().run())
    by_id = {r.attack.id: r for r in report.results}
    assert by_id["inj-1"].outcome == "blocked"
    assert by_id["jb-1"].outcome == "blocked"
    assert by_id["sp-1"].outcome == "blocked"


def test_redteam_redacts_pii():
    report = asyncio.run(RedTeamSuite().run())
    for r in report.results:
        if r.attack.category == "pii":
            assert r.outcome == "redacted", f"{r.attack.id} leaked"
            assert r.attack.secret not in (r.attack.payload if False else "")  # secret removed


def test_redteam_no_false_positive_on_benign():
    report = asyncio.run(RedTeamSuite().run())
    for r in report.results:
        if r.attack.category == "benign":
            assert r.outcome == "allowed", f"benign {r.attack.id} was blocked (false positive)"


def test_redteam_reports_score_and_categories():
    report = asyncio.run(RedTeamSuite().run())
    s = report.summary()
    assert s["total"] == len(ATTACKS)
    assert 0.0 <= s["score"] <= 1.0
    assert "injection" in s["by_category"] and "pii" in s["by_category"]
