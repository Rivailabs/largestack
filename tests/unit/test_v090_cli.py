"""v0.9.0: Tests for the enhanced CLI commands."""
from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


# -------------------- init command --------------------

def test_init_creates_simple_agent(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "myproject"
    rc = cmd_init_v09("simple_agent", str(target))
    assert rc == 0
    assert (target / "agent.yaml").exists()
    assert (target / "main.py").exists()
    assert (target / "README.md").exists()


def test_init_creates_rag_app(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "rag"
    rc = cmd_init_v09("rag_app", str(target))
    assert rc == 0
    assert (target / "agent.yaml").exists()
    assert (target / "ingest.py").exists()


def test_init_creates_multi_agent(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "ma"
    rc = cmd_init_v09("multi_agent", str(target))
    assert rc == 0
    assert (target / "workflow.yaml").exists()


def test_init_creates_fintech_app(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "ft"
    rc = cmd_init_v09("fintech_app", str(target))
    assert rc == 0
    content = (target / "agent.yaml").read_text()
    assert "DPDP_Act_2023" in content
    assert "kyc_verify_pan" in content


def test_init_creates_legaltech_app(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "lt"
    rc = cmd_init_v09("legaltech_app", str(target))
    assert rc == 0


def test_init_rejects_unknown_template(tmp_path, capsys):
    from largestack._cli.cli_v09 import cmd_init_v09
    rc = cmd_init_v09("nonexistent", str(tmp_path / "x"))
    assert rc == 1
    captured = capsys.readouterr()
    assert "unknown template" in captured.out


def test_init_rejects_non_empty_dir(tmp_path):
    from largestack._cli.cli_v09 import cmd_init_v09
    target = tmp_path / "existing"
    target.mkdir()
    (target / "file.txt").write_text("x")
    rc = cmd_init_v09("simple_agent", str(target))
    assert rc == 1


# -------------------- pii-scan command --------------------

def test_pii_scan_finds_pan(tmp_path):
    from largestack._cli.cli_v09 import cmd_pii_scan
    f = tmp_path / "test.txt"
    f.write_text("My PAN is AAACR1234C and email me@example.com")
    rc = cmd_pii_scan(str(f))
    # Found PII → exit code 2
    assert rc == 2


def test_pii_scan_finds_aadhaar(tmp_path, capsys):
    from largestack._cli.cli_v09 import cmd_pii_scan
    f = tmp_path / "test.txt"
    f.write_text("Aadhaar: 234567890123 should be redacted")
    rc = cmd_pii_scan(str(f))
    captured = capsys.readouterr()
    assert "AADHAAR" in captured.out
    assert rc == 2


def test_pii_scan_no_findings(tmp_path):
    from largestack._cli.cli_v09 import cmd_pii_scan
    f = tmp_path / "clean.txt"
    f.write_text("No personal data here, just clean text.")
    rc = cmd_pii_scan(str(f))
    assert rc == 0


def test_pii_scan_directory_recursive(tmp_path):
    from largestack._cli.cli_v09 import cmd_pii_scan
    (tmp_path / "f1.txt").write_text("PAN: AAACR1234C")
    (tmp_path / "f2.md").write_text("safe content")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "f3.log").write_text("Aadhaar 234567890123 found")
    rc = cmd_pii_scan(str(tmp_path))
    assert rc == 2  # PII found


def test_pii_scan_json_output(tmp_path, capsys):
    from largestack._cli.cli_v09 import cmd_pii_scan
    f = tmp_path / "x.txt"
    f.write_text("PAN AAACR1234C")
    rc = cmd_pii_scan(str(f), json_output=True)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "files_scanned" in data
    assert "findings" in data


def test_pii_scan_path_not_found(tmp_path):
    from largestack._cli.cli_v09 import cmd_pii_scan
    rc = cmd_pii_scan(str(tmp_path / "nonexistent.txt"))
    assert rc == 1


def test_pii_scan_redacts_in_output(tmp_path, capsys):
    """PAN should be partially masked in console output."""
    from largestack._cli.cli_v09 import cmd_pii_scan
    f = tmp_path / "x.txt"
    f.write_text("AAACR1234C")
    cmd_pii_scan(str(f))
    captured = capsys.readouterr()
    # Full PAN should NOT appear unmasked
    assert "AAACR1234C" not in captured.out
    # But masked version should
    assert "AAAC***" in captured.out


# -------------------- tenant command --------------------

def test_tenant_create(tmp_path):
    from largestack._cli.cli_v09 import cmd_tenant
    rc = cmd_tenant("create", "tenant_a", str(tmp_path))
    assert rc == 0
    storage = tmp_path / "tenants.json"
    data = json.loads(storage.read_text())
    assert "tenant_a" in data
    assert data["tenant_a"]["active"] is True


def test_tenant_create_duplicate_fails(tmp_path):
    from largestack._cli.cli_v09 import cmd_tenant
    cmd_tenant("create", "x", str(tmp_path))
    rc = cmd_tenant("create", "x", str(tmp_path))
    assert rc == 1


def test_tenant_list(tmp_path, capsys):
    from largestack._cli.cli_v09 import cmd_tenant
    cmd_tenant("create", "alpha", str(tmp_path))
    cmd_tenant("create", "beta", str(tmp_path))
    capsys.readouterr()  # clear
    rc = cmd_tenant("list", "", str(tmp_path))
    captured = capsys.readouterr()
    assert "alpha" in captured.out
    assert "beta" in captured.out
    assert rc == 0


def test_tenant_delete(tmp_path):
    from largestack._cli.cli_v09 import cmd_tenant
    cmd_tenant("create", "todelete", str(tmp_path))
    rc = cmd_tenant("delete", "todelete", str(tmp_path))
    assert rc == 0
    storage = tmp_path / "tenants.json"
    data = json.loads(storage.read_text())
    assert "todelete" not in data


def test_tenant_delete_nonexistent(tmp_path):
    from largestack._cli.cli_v09 import cmd_tenant
    rc = cmd_tenant("delete", "nope", str(tmp_path))
    assert rc == 1


def test_tenant_create_requires_name(tmp_path):
    from largestack._cli.cli_v09 import cmd_tenant
    rc = cmd_tenant("create", "", str(tmp_path))
    assert rc == 1


# -------------------- audit-export command --------------------

def test_audit_export_collects_logs(tmp_path):
    from largestack._cli.cli_v09 import cmd_audit_export
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "audit_20260501.log").write_text(
        '{"event": "tool_call", "ts": 1}\n'
        '{"event": "agent_run", "ts": 2}\n'
    )
    (log_dir / "audit_20260502.jsonl").write_text(
        '{"event": "tool_call", "ts": 3}\n'
    )

    out = tmp_path / "export.jsonl"
    rc = cmd_audit_export(str(out), str(log_dir))
    assert rc == 0
    lines = out.read_text().strip().splitlines()
    assert len(lines) == 3


def test_audit_export_no_logs_found(tmp_path):
    from largestack._cli.cli_v09 import cmd_audit_export
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    rc = cmd_audit_export(str(tmp_path / "out.jsonl"), str(empty_dir))
    assert rc == 1


def test_audit_export_missing_source_dir(tmp_path):
    from largestack._cli.cli_v09 import cmd_audit_export
    rc = cmd_audit_export(str(tmp_path / "out.jsonl"), str(tmp_path / "nope"))
    assert rc == 1


# -------------------- eval command --------------------

def test_eval_runs_yaml_suite(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v09 import cmd_eval
    suite = tmp_path / "suite.yaml"
    suite.write_text("""\
cases:
  - name: test1
    input: hello
    expected: hi
  - name: test2
    input: x
""")
    rc = cmd_eval(str(suite))
    # 1 PASS (has expected), 1 SKIP
    assert rc == 0


def test_eval_missing_suite():
    from largestack._cli.cli_v09 import cmd_eval
    rc = cmd_eval("/nonexistent/suite.yaml")
    assert rc == 1


# -------------------- argparse main --------------------

def test_cli_main_init(tmp_path):
    from largestack._cli.cli_v09 import main
    rc = main(["init", "simple_agent", str(tmp_path / "p1")])
    assert rc == 0


def test_cli_main_pii_scan(tmp_path):
    from largestack._cli.cli_v09 import main
    f = tmp_path / "x.txt"
    f.write_text("clean")
    rc = main(["pii-scan", str(f)])
    assert rc == 0


def test_cli_main_tenant_list(tmp_path, capsys):
    from largestack._cli.cli_v09 import main
    rc = main(["tenant", "list", "--tenant-dir", str(tmp_path)])
    assert rc == 0


def test_cli_main_unknown_command():
    from largestack._cli.cli_v09 import main
    with pytest.raises(SystemExit):  # argparse exits on unknown
        main(["nonexistent-cmd"])
