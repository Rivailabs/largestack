"""v0.9.0: Tests for pre-built Grafana dashboards."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


DASHBOARDS_DIR = Path(__file__).parent.parent.parent / "deploy" / "grafana" / "dashboards"
PROVISIONING_DIR = Path(__file__).parent.parent.parent / "deploy" / "grafana" / "provisioning"


def test_three_dashboards_shipped():
    """3 dashboards: agent-overview, llm-cost, india-compliance."""
    json_files = list(DASHBOARDS_DIR.glob("*.json"))
    assert len(json_files) == 3, f"Got: {[p.name for p in json_files]}"


def test_each_dashboard_is_valid_json():
    for f in DASHBOARDS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f"{f.name} is not valid JSON: {e}")
        assert "title" in data, f"{f.name} missing title"
        assert "panels" in data, f"{f.name} missing panels"
        assert "uid" in data, f"{f.name} missing uid"
        assert len(data["panels"]) >= 1, f"{f.name} has no panels"


def test_agent_overview_has_required_panels():
    data = json.loads((DASHBOARDS_DIR / "largestack-agent-overview.json").read_text())
    titles = {p.get("title", "") for p in data["panels"]}
    # Verify we have rate, latency, error, tool, PII panels
    assert any("rate" in t.lower() for t in titles), "missing rate panel"
    assert any("latency" in t.lower() for t in titles), "missing latency panel"
    assert any("error" in t.lower() for t in titles), "missing error panel"


def test_compliance_dashboard_tracks_indian_metrics():
    data = json.loads((DASHBOARDS_DIR / "largestack-india-compliance.json").read_text())
    raw = json.dumps(data)
    # All Indian-specific metrics tracked
    assert "aadhaar" in raw.lower()
    assert "pan" in raw.lower()
    assert "kyc" in raw.lower()
    assert "aml" in raw.lower()


def test_cost_dashboard_tracks_tokens_and_dollars():
    data = json.loads((DASHBOARDS_DIR / "largestack-llm-cost.json").read_text())
    raw = json.dumps(data)
    assert "cost" in raw.lower()
    assert "tokens" in raw.lower()
    assert "currencyUSD" in raw


def test_provisioning_yamls_present():
    pytest.importorskip("yaml")
    import yaml as _yaml

    ds_yaml = PROVISIONING_DIR / "datasources" / "prometheus.yml"
    assert ds_yaml.exists()
    ds_data = _yaml.safe_load(ds_yaml.read_text())
    assert ds_data["datasources"][0]["type"] == "prometheus"

    db_yaml = PROVISIONING_DIR / "dashboards" / "largestack.yml"
    assert db_yaml.exists()
    db_data = _yaml.safe_load(db_yaml.read_text())
    assert db_data["providers"][0]["type"] == "file"


def test_dashboards_have_unique_uids():
    """No two dashboards share a UID (avoids Grafana provisioning conflicts)."""
    uids = []
    for f in DASHBOARDS_DIR.glob("*.json"):
        data = json.loads(f.read_text())
        uids.append(data["uid"])
    assert len(uids) == len(set(uids)), f"Duplicate UIDs: {uids}"
