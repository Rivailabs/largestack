"""v0.12.0: Tests for CLI commands (eval-block + studio-export)."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest


# Minimal eval suite that should pass
SAMPLE_PASSING_SUITE = textwrap.dedent("""\
    name: smoke-test
    judge: openai/gpt-4o-mini
    threshold: 0.5
    cases:
      - name: case_1
        input: hello
        contains: ["hello"]
      - name: case_2
        input: world
        contains: ["world"]
""")


# Eval suite designed to fail (echo runner can't satisfy these)
SAMPLE_FAILING_SUITE = textwrap.dedent("""\
    name: failing-test
    judge: openai/gpt-4o-mini
    threshold: 0.5
    cases:
      - name: case_1
        input: foo
        contains: ["nonexistent_word_xyz"]
      - name: case_2
        input: bar
        contains: ["another_missing_xyz"]
""")


# -------------------- Parser tests --------------------

def test_parser_includes_eval_block():
    from largestack._cli.cli_v120 import build_parser
    p = build_parser()
    args = p.parse_args(["eval-block", "/tmp/x.yaml"])
    assert args.cmd == "eval-block"
    assert args.suite == "/tmp/x.yaml"


def test_parser_default_fail_under():
    from largestack._cli.cli_v120 import build_parser, DEFAULT_FAIL_UNDER
    p = build_parser()
    args = p.parse_args(["eval-block", "x.yaml"])
    assert args.fail_under == DEFAULT_FAIL_UNDER


def test_parser_custom_fail_under():
    from largestack._cli.cli_v120 import build_parser
    p = build_parser()
    args = p.parse_args([
        "eval-block", "x.yaml", "--fail-under", "0.85",
    ])
    assert args.fail_under == 0.85


def test_parser_studio_export_requires_agent_and_output():
    from largestack._cli.cli_v120 import build_parser
    p = build_parser()
    args = p.parse_args([
        "studio-export", "--agent", "a.yaml", "-o", "out.html",
    ])
    assert args.cmd == "studio-export"
    assert args.agent == "a.yaml"
    assert args.output == "out.html"


# -------------------- eval-block: missing suite --------------------

def test_eval_block_missing_suite_returns_error_code(tmp_path, capsys):
    from largestack._cli.cli_v120 import main, EXIT_ERROR
    code = main([
        "eval-block",
        str(tmp_path / "nope.yaml"),
        "--quiet",
    ])
    assert code == EXIT_ERROR
    err = capsys.readouterr().err
    assert "not found" in err.lower()


# -------------------- eval-block: passing suite returns 0 --------------------

def test_eval_block_passing_suite_returns_zero(tmp_path):
    from largestack._cli.cli_v120 import main, EXIT_OK

    suite = tmp_path / "smoke.yaml"
    suite.write_text(SAMPLE_PASSING_SUITE)

    code = main([
        "eval-block", str(suite),
        "--fail-under", "0.5",
        "--quiet",
    ])
    assert code == EXIT_OK


# -------------------- eval-block: failing suite exits non-zero --------------------

def test_eval_block_failing_suite_exits_nonzero(tmp_path, capsys):
    from largestack._cli.cli_v120 import main, EXIT_FAIL_UNDER

    suite = tmp_path / "fail.yaml"
    suite.write_text(SAMPLE_FAILING_SUITE)

    code = main([
        "eval-block", str(suite),
        "--fail-under", "0.5",
        "--quiet",
    ])
    assert code == EXIT_FAIL_UNDER
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "below threshold" in err


# -------------------- eval-block: --junit writes XML --------------------

def test_eval_block_writes_junit_xml(tmp_path):
    from largestack._cli.cli_v120 import main

    suite = tmp_path / "smoke.yaml"
    suite.write_text(SAMPLE_PASSING_SUITE)
    junit_path = tmp_path / "junit.xml"

    code = main([
        "eval-block", str(suite),
        "--fail-under", "0.5",
        "--junit", str(junit_path),
        "--quiet",
    ])
    assert code == 0
    assert junit_path.exists()
    content = junit_path.read_text()
    assert "<?xml" in content
    assert "testsuite" in content


# -------------------- eval-block: --json-out writes JSON --------------------

def test_eval_block_writes_json(tmp_path):
    from largestack._cli.cli_v120 import main

    suite = tmp_path / "smoke.yaml"
    suite.write_text(SAMPLE_PASSING_SUITE)
    json_path = tmp_path / "report.json"

    code = main([
        "eval-block", str(suite),
        "--fail-under", "0.5",
        "--json-out", str(json_path),
        "--quiet",
    ])
    assert code == 0
    assert json_path.exists()
    data = json.loads(json_path.read_text())
    assert data["name"] == "smoke-test"
    assert "summary" in data
    assert data["summary"]["total"] == 2


# -------------------- eval-block: high threshold fails passing suite --------------------

def test_eval_block_high_threshold_fails_otherwise_passing(tmp_path):
    """If --fail-under is set very high, even a passing suite exits non-zero."""
    from largestack._cli.cli_v120 import main, EXIT_FAIL_UNDER

    suite = tmp_path / "smoke.yaml"
    suite.write_text(SAMPLE_PASSING_SUITE)

    code = main([
        "eval-block", str(suite),
        "--fail-under", "1.01",  # impossible
        "--quiet",
    ])
    assert code == EXIT_FAIL_UNDER


# -------------------- studio-export --------------------

def test_studio_export_writes_html(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v120 import main

    agent_yaml = tmp_path / "agent.yaml"
    agent_yaml.write_text(textwrap.dedent("""\
        name: my-test-agent
        description: A test agent for KYC
        model: openai/gpt-4o-mini
        tools:
          - aadhaar_okyc
          - pan_verify
        compliance:
          - DPDP_Act_2023
          - RBI_PA_PG_2024
    """))

    out = tmp_path / "studio.html"
    code = main([
        "studio-export",
        "--agent", str(agent_yaml),
        "-o", str(out),
        "--quiet",
    ])
    assert code == 0
    assert out.exists()
    content = out.read_text()
    # Title comes through
    assert "my-test-agent" in content
    # Tools become nodes
    assert "aadhaar_okyc" in content
    assert "pan_verify" in content
    # Compliance markers
    assert "DPDP_Act_2023" in content


def test_studio_export_with_audit_log(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v120 import main

    agent_yaml = tmp_path / "agent.yaml"
    agent_yaml.write_text(
        "name: x\ndescription: y\nmodel: m\n",
    )

    audit_log = tmp_path / "audit.json"
    audit_log.write_text(json.dumps([
        {
            "timestamp": 1000.0,
            "agent": "kyc",
            "event": "pan_verify",
            "payload": {"pan": "AAACR1234C"},
        },
    ]))

    out = tmp_path / "studio.html"
    code = main([
        "studio-export",
        "--agent", str(agent_yaml),
        "-o", str(out),
        "--audit-log", str(audit_log),
        "--quiet",
    ])
    assert code == 0
    content = out.read_text()
    assert "pan_verify" in content


def test_studio_export_missing_agent(tmp_path, capsys):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v120 import main, EXIT_ERROR
    code = main([
        "studio-export",
        "--agent", str(tmp_path / "nope.yaml"),
        "-o", str(tmp_path / "out.html"),
        "--quiet",
    ])
    assert code == EXIT_ERROR
    assert "not found" in capsys.readouterr().err.lower()


# -------------------- main without subcommand --------------------

def test_main_without_subcommand_shows_help(capsys):
    from largestack._cli.cli_v120 import main, EXIT_USAGE
    code = main([])
    assert code == EXIT_USAGE


# -------------------- exit code constants --------------------

def test_exit_code_constants_are_distinct():
    from largestack._cli.cli_v120 import (
        EXIT_OK, EXIT_FAIL_UNDER, EXIT_USAGE, EXIT_ERROR,
    )
    assert EXIT_OK == 0
    assert len({EXIT_OK, EXIT_FAIL_UNDER, EXIT_USAGE, EXIT_ERROR}) == 4
