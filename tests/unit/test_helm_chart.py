"""Helm chart structural test (v0.4.0).

Doesn't require helm CLI — validates chart structure and required content
so we catch regressions when files are added/renamed.
"""
from pathlib import Path

import pytest
import yaml


CHART_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "deploy" / "helm" / "largestack"
)


def test_chart_yaml_present_and_valid():
    chart = yaml.safe_load((CHART_DIR / "Chart.yaml").read_text())
    assert chart["name"] == "largestack"
    assert chart["apiVersion"] == "v2"
    assert "version" in chart
    assert "appVersion" in chart


def test_values_yaml_required_keys():
    """values.yaml must declare every key the templates reference."""
    values = yaml.safe_load((CHART_DIR / "values.yaml").read_text())
    required_top = [
        "image", "replicaCount", "resources", "service", "ingress",
        "autoscaling", "largestack", "otel", "podSecurityContext",
        "securityContext", "serviceAccount",
    ]
    for key in required_top:
        assert key in values, f"missing required values key: {key}"

    # Image fields
    for key in ("repository", "tag", "pullPolicy"):
        assert key in values["image"]

    # Service fields
    assert "port" in values["service"]
    assert values["service"]["port"] == 8000


def test_required_templates_present():
    """All expected templates must exist."""
    required = [
        "deployment.yaml", "service.yaml", "configmap.yaml",
        "serviceaccount.yaml", "ingress.yaml", "hpa.yaml", "_helpers.tpl",
    ]
    for name in required:
        path = CHART_DIR / "templates" / name
        assert path.exists(), f"missing template: {name}"
        assert path.stat().st_size > 0, f"empty template: {name}"


def test_chart_uses_external_secret_reference():
    """The canonical chart must keep provider secrets out of values.yaml."""
    values = yaml.safe_load((CHART_DIR / "values.yaml").read_text())
    assert values["largestack"]["envFromSecret"] == "largestack-secrets"


def test_deployment_uses_health_probes():
    """Deployment must define liveness + readiness probes hitting /health."""
    src = (CHART_DIR / "templates" / "deployment.yaml").read_text()
    assert "livenessProbe" in src
    assert "readinessProbe" in src
    assert "/health" in src


def test_security_defaults_are_strict():
    """Pod and container security contexts default to non-root + no privesc."""
    values = yaml.safe_load((CHART_DIR / "values.yaml").read_text())
    sc = values["securityContext"]
    assert sc["runAsNonRoot"] is True
    assert sc["runAsUser"] == 1001
    assert sc["allowPrivilegeEscalation"] is False
    assert sc["capabilities"]["drop"] == ["ALL"]


def test_chart_readme_exists():
    """Operators need install/upgrade/uninstall docs."""
    readme = (CHART_DIR / "README.md").read_text()
    for keyword in ("helm install", "helm upgrade", "helm uninstall"):
        assert keyword in readme, f"README missing {keyword!r}"
