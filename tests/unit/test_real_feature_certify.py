from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "largestack_real_feature_certify",
    ROOT / "scripts" / "largestack_real_feature_certify.py",
)
cert = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["largestack_real_feature_certify"] = cert
SPEC.loader.exec_module(cert)


def test_real_feature_suite_has_26_specs_with_bfsi_additions():
    specs = cert.make_real_feature_specs()
    assert len(specs) == 26
    assert len({item.name for item in specs}) == 26
    assert specs[-2].name == "bfsi_loan_origination_maker_checker"
    assert specs[-1].name == "bfsi_aml_transaction_monitoring"
    assert all("README.md" in item.required_files for item in specs)
    assert all("largestack_app.py" in item.required_files for item in specs)


def test_real_feature_specs_have_known_feature_contracts():
    specs = cert.make_real_feature_specs()
    known = set(cert.FEATURES)
    for spec in specs:
        assert spec.evidence_required
        assert set(spec.evidence_required) <= known
        assert "run_largestack_smoke" in spec.acceptance


def test_bfsi_specs_require_no_external_side_effects():
    specs = {item.name: item for item in cert.make_real_feature_specs()}
    loan = specs["bfsi_loan_origination_maker_checker"]
    aml = specs["bfsi_aml_transaction_monitoring"]
    assert "executed False" in loan.requirements
    assert "approval_required" in loan.acceptance
    assert "filed False" in aml.requirements
    assert "insufficient evidence" in aml.acceptance
    assert "disburse_funds" in loan.forbidden_actions
    assert "file_sar" in aml.forbidden_actions


def test_b2b_agentic_suite_has_24_market_focused_specs():
    specs = cert.make_b2b_agentic_specs()
    assert len(specs) == 24
    assert len({item.name for item in specs}) == 24
    assert all(item.name.startswith("b2b_") for item in specs)
    assert specs[0].name == "b2b_sales_forecast_copilot"
    assert specs[-1].name == "b2b_msp_ticket_router_sla_agent"
    assert all("README.md" in item.required_files for item in specs)
    assert all("largestack_app.py" in item.required_files for item in specs)
    assert all(item.classification == "DEEPSEEK-BUILT-LARGESTACK-B2B-AGENTIC-PROJECT" for item in specs)


def test_b2b_agentic_specs_are_real_feature_specs():
    known = set(cert.FEATURES)
    specs = cert.make_b2b_agentic_specs()
    covered = set()
    for spec in specs:
        assert spec.evidence_required
        assert set(spec.evidence_required) <= known
        covered.update(spec.evidence_required)
        assert "run_largestack_smoke" in spec.acceptance
        assert "Public usage contract" in spec.requirements
        assert "external side effects" in spec.requirements
        assert "network calls" in spec.requirements
    assert covered == known


def test_b2b_agentic_specs_gate_risky_actions():
    specs = {item.name: item for item in cert.make_b2b_agentic_specs()}
    invoice = specs["b2b_invoice_reconciliation_agent"]
    incident = specs["b2b_incident_response_war_room"]
    cloud = specs["b2b_cloud_cost_anomaly_assistant"]
    msp = specs["b2b_msp_ticket_router_sla_agent"]
    assert "release_payment" in invoice.forbidden_actions
    assert "send_customer_notice" in incident.forbidden_actions
    assert "shutdown_instance" in cloud.forbidden_actions
    assert "send_pagerduty" in msp.forbidden_actions
    assert "executed'] is False" in invoice.acceptance
    assert "notify_executed'] is False" in msp.acceptance


def test_suite_selector_uses_stricter_b2b_thresholds():
    feature_specs, feature_min, feature_avg, feature_label = cert.select_specs_for_suite("features")
    b2b_specs, b2b_min, b2b_avg, b2b_label = cert.select_specs_for_suite("b2b")
    all_specs, all_min, all_avg, all_label = cert.select_specs_for_suite("all")
    assert len(feature_specs) == 26
    assert feature_min == 90
    assert feature_avg == 95.0
    assert feature_label == "real-feature"
    assert len(b2b_specs) == 24
    assert b2b_min == 95
    assert b2b_avg == 98.0
    assert b2b_label == "b2b-agentic"
    assert len(all_specs) == 50
    assert all_min == 95
    assert all_avg == 98.0
    assert all_label == "combined-real-feature-and-b2b-agentic"
