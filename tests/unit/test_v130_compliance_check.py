"""v0.13.0: Tests for the ``compliance-check`` CLI command."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# -------------------- Smoke / module --------------------

def test_compliance_module_imports():
    from largestack._cli import cli_v130_compliance
    assert hasattr(cli_v130_compliance, "run_compliance_check")
    assert hasattr(cli_v130_compliance, "add_compliance_check_parser")


# -------------------- File handling --------------------

def test_missing_file_returns_error_finding(tmp_path):
    from largestack._cli.cli_v130_compliance import run_compliance_check
    report = run_compliance_check(tmp_path / "nope.yaml")
    assert not report.passed
    assert any("not found" in f.message for f in report.errors)


def test_invalid_yaml_returns_error(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "bad.yaml", "[1, 2, 3")  # malformed
    report = run_compliance_check(p)
    assert not report.passed


# -------------------- C001-C005: compliance markers --------------------

def test_no_compliance_section_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: my-agent
        model: openai/gpt-4o-mini
    """)
    report = run_compliance_check(p)
    assert not report.passed
    codes = {f.code for f in report.errors}
    assert "C001" in codes


def test_dpdp_marker_present_passes_marker_check(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: my-agent
        model: openai/gpt-4o-mini
        tenant_id: '{{ env.TENANT_ID }}'
        audit:
          enabled: true
          retention_days: 2920
        compliance:
          - name: DPDP_Act_2023
            section: Section 6
    """)
    report = run_compliance_check(p)
    # No C001 / C005 errors (DPDP marker found)
    error_codes = {f.code for f in report.errors}
    assert "C001" not in error_codes
    assert "C005" not in error_codes


# -------------------- C010-C012: sector requirements --------------------

def test_financial_sector_without_rbi_marker_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: nbfc-agent
        sector: financial
        model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
        region: ap-south-1
        tenant_id: '{{ env.TENANT_ID }}'
        audit:
          enabled: true
        compliance:
          - name: DPDP_Act_2023
            section: Section 6
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C010" in codes  # missing RBI


def test_financial_sector_with_rbi_marker_passes(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: nbfc-agent
        sector: financial
        model: bedrock/anthropic.claude-3-haiku-20240307-v1:0
        region: ap-south-1
        tenant_id: '{{ env.TENANT_ID }}'
        audit:
          enabled: true
          retention_days: 2920
        compliance:
          - name: DPDP_Act_2023
            section: Section 6
          - name: RBI MD-NBFC-D
            section: NBFC
          - name: PMLA Rule 9
            section: CDD
    """)
    report = run_compliance_check(p)
    assert report.passed, report.render()


# -------------------- C020-C021: tenant parameterization --------------------

def test_hardcoded_tenant_id_warns(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: production
        audit: {enabled: true}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.warnings}
    assert "C021" in codes


def test_templated_tenant_id_no_warn(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.TENANT_ID }}'
        audit: {enabled: true}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.warnings}
    assert "C021" not in codes


# -------------------- C030-C032: audit --------------------

def test_no_audit_section_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C030" in codes


def test_audit_disabled_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit:
          enabled: false
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C031" in codes


def test_short_audit_retention_warns(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit:
          enabled: true
          retention_days: 365
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.warnings}
    assert "C032" in codes


# -------------------- C040-C041: PII tools --------------------

def test_pii_tool_without_purpose_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit: {enabled: true}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
        tools:
          - name: aadhaar_verify
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C040" in codes  # missing purpose
    assert "C041" in codes  # missing lawful_basis


def test_pii_tool_with_full_markers_passes(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit: {enabled: true}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
        tools:
          - name: aadhaar_verify
            purpose: KYC verification
            lawful_basis: consent
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C040" not in codes
    assert "C041" not in codes


# -------------------- C050: LLM residency --------------------

def test_china_llm_in_financial_sector_fails(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_compliance_check

    p = _write(tmp_path, "a.yaml", """
        name: a
        sector: financial
        model: deepseek/chat
        tenant_id: '{{ env.X }}'
        audit: {enabled: true}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
          - {name: RBI MD-NBFC-D, section: NBFC}
    """)
    report = run_compliance_check(p)
    codes = {f.code for f in report.errors}
    assert "C050" in codes


# -------------------- argparse + run_from_args --------------------

def test_argparse_run_from_args_returns_zero_on_pass(
    tmp_path, capsys,
):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_from_args
    import argparse

    p = _write(tmp_path, "good.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit: {enabled: true, retention_days: 2920}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)

    args = argparse.Namespace(
        agent=str(p), strict=False, sector=None, quiet=True,
    )
    rc = run_from_args(args)
    assert rc == 0


def test_argparse_run_from_args_returns_nonzero_on_fail(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_from_args
    import argparse

    p = _write(tmp_path, "bad.yaml", """
        name: missing-everything
    """)
    args = argparse.Namespace(
        agent=str(p), strict=False, sector=None, quiet=True,
    )
    rc = run_from_args(args)
    assert rc != 0


def test_strict_mode_fails_on_warnings(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v130_compliance import run_from_args
    import argparse

    # Has warnings but no errors
    p = _write(tmp_path, "warn.yaml", """
        name: a
        tenant_id: production
        audit: {enabled: true, retention_days: 2920}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    args = argparse.Namespace(
        agent=str(p), strict=True, sector=None, quiet=True,
    )
    rc = run_from_args(args)
    assert rc != 0


def test_main_dispatches_compliance_check(tmp_path):
    pytest.importorskip("yaml")
    from largestack._cli.cli_v120 import main

    p = _write(tmp_path, "good.yaml", """
        name: a
        tenant_id: '{{ env.X }}'
        audit: {enabled: true, retention_days: 2920}
        compliance:
          - {name: DPDP_Act_2023, section: Section 6}
    """)
    rc = main(["compliance-check", str(p), "--quiet"])
    assert rc == 0
