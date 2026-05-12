from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from largestack.autonomous_builder import BuildReport, ValidationResult


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("final_95_plus_certify", ROOT / "scripts" / "final_95_plus_certify.py")
cert = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["final_95_plus_certify"] = cert
SPEC.loader.exec_module(cert)


def _report(tmp_path: Path, *, passed: bool = True) -> BuildReport:
    validation = ValidationResult(
        compile_passed=passed,
        pytest_passed=passed,
        acceptance_passed=passed,
        validation_output="ok",
        acceptance_output="ok",
        failed_checks=[] if passed else ["acceptance"],
    )
    return BuildReport(
        name="x",
        passed=passed,
        project_path=str(tmp_path),
        generated_files=["app.py", "README.md", "tests/test_app.py"],
        validation=validation,
        trace_ids=["trace-1"],
        tokens=1000,
        actual_cost=0.01,
        estimated_cost=0.01,
        attempts=[],
    )


def test_final_certification_has_24_project_specs():
    specs = cert.make_specs()
    assert len(specs) == 24
    assert len({item.name for item in specs}) == 24
    assert all("README.md" in item.required_files for item in specs)
    assert all("Public usage contract" in item.requirements for item in specs)


def test_deterministic_score_reaches_95_for_clean_project(tmp_path):
    score = cert.deterministic_score(_report(tmp_path), security_ok=True, readme_ok=True)
    assert score.deterministic_total == 100


def test_security_scan_flags_realistic_secret_and_network_import(tmp_path):
    fake_key = "sk-" + "abc12345678901234567890"
    (tmp_path / "app.py").write_text(f"import requests\nTOKEN='{fake_key}'\n")
    ok, issues = cert.scan_project_security(tmp_path)
    assert ok is False
    assert any("possible secret" in item for item in issues)
    assert any("network side effect" in item for item in issues)


def test_security_scan_does_not_flag_plain_word_requests(tmp_path):
    (tmp_path / "app.py").write_text("def text():\n    return 'refund requests require approval'\n")
    ok, issues = cert.scan_project_security(tmp_path)
    assert ok is True
    assert issues == []


def test_reviewer_json_parses_fenced_output():
    data = cert.parse_reviewer_json('```json\n{"score": 97, "pass": true, "notes": "ok"}\n```')
    assert data["score"] == 97
    assert data["pass"] is True


def test_run_cmd_classifies_missing_binary_as_env_blocker(tmp_path):
    gate = cert.run_cmd("missing_tool", ["largestack-definitely-missing-binary"], tmp_path, timeout=1)
    assert gate.status == "FAIL"
    assert gate.blocker_type == "ENV BLOCKER"
    assert "missing command" in gate.reason


def test_reviewer_warning_is_overridden_when_direct_validation_passes(tmp_path):
    score = cert.deterministic_score(_report(tmp_path), security_ok=True, readme_ok=True)
    reviewer = cert.ReviewerOutcome(
        score=0,
        json_valid=True,
        passed=False,
        notes="claims syntax failure",
        critical_blocker="syntax failure",
    )
    outcome = cert.reconcile_reviewer_with_validation(
        score,
        reviewer,
        report=_report(tmp_path),
        security_ok=True,
        readme_ok=True,
    )
    assert outcome.passed is True
    assert outcome.score == 90
    assert outcome.critical_blocker == ""


def test_compute_scores_holds_bfsi_without_external_audit(tmp_path, monkeypatch):
    gates = [
        cert.GateResult(name="baseline_final_release_validate", status="PASS"),
        cert.GateResult(name="security_tests", status="PASS"),
        cert.GateResult(name="docker_runtime_auth_cleanup", status="PASS"),
    ]
    projects = [
        cert.ProjectCertification(
            name=f"p{i}",
            passed=True,
            score=96,
            blocker_type="PASS",
            solution="",
            report_path=str(tmp_path / f"p{i}.json"),
            project_path=str(tmp_path / f"p{i}"),
        )
        for i in range(24)
    ]
    monkeypatch.delenv("LARGESTACK_EXTERNAL_AUDIT_PASSED", raising=False)
    scores = cert.compute_scores(gates, projects)
    assert scores["real_project_generation"] >= 95
    assert scores["saas"] >= 95
    assert scores["bfsi"] == 85.0
