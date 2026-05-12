from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "load_soak_certify.py"


def load_module():
    spec = importlib.util.spec_from_file_location("load_soak_certify", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_percentile_and_redaction_helpers():
    mod = load_module()
    assert mod.percentile([10.0, 20.0, 30.0], 0.50) == 20.0
    assert "[REDACTED]" in mod.redact_text("token=abc1234567890")


def test_scenario_registry_includes_mixed_and_failure_paths():
    mod = load_module()
    scenarios = mod.build_scenarios(include_failure_injections=True)
    names = {s.name for s in scenarios}
    assert {
        "agent_run",
        "typed_agent_tools",
        "team_parallel",
        "workflow_dag",
        "orchestrator_router",
        "rag_guardrails",
        "memory_isolation",
        "structured_output",
        "tool_error_handled",
        "provider_timeout_handled",
        "bad_key_handled",
        "rate_limit_handled",
    }.issubset(names)
    assert [s.name for s in mod.build_scenarios(True, "lightweight")] == ["agent_run"]


def test_run_certification_writes_evidence(tmp_path):
    outdir = tmp_path / "unit-load-soak"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--run-id",
            "unit-load-soak",
            "--outdir",
            str(outdir),
            "--total-runs",
            "12",
            "--concurrency",
            "3",
            "--target-success-rate",
            "1.0",
            "--max-memory-growth-mb",
            "512",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads((outdir / "summary.json").read_text(encoding="utf-8"))
    assert summary["decision"] == "PASS"
    assert summary["metrics"]["total"] == 12
    assert summary["metrics"]["failed"] == 0
    assert summary["metrics"]["expected_failures_handled"] == 4
    assert (outdir / "events.jsonl").exists()
    assert (outdir / "summary.json").exists()
    assert (outdir / "SUMMARY.md").exists()
