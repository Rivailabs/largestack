"""v0.10.0: Tests for the Helm chart files."""

from __future__ import annotations

from pathlib import Path

import pytest


HELM_DIR = Path(__file__).parent.parent.parent / "deploy" / "helm" / "largestack"


def test_helm_chart_yaml_present():
    assert (HELM_DIR / "Chart.yaml").exists()


def test_helm_chart_metadata():
    pytest.importorskip("yaml")
    import yaml as _yaml

    chart = _yaml.safe_load((HELM_DIR / "Chart.yaml").read_text())
    assert chart["apiVersion"] == "v2"
    assert chart["name"] == "largestack"
    # Version matches the package version
    assert chart["version"] == "1.0.0"
    assert chart["appVersion"] == "1.0.0"
    # Dependencies for redis + postgres
    deps = {d["name"] for d in chart.get("dependencies", [])}
    assert "redis" in deps
    assert "postgresql" in deps


def test_helm_values_yaml_present():
    pytest.importorskip("yaml")
    import yaml as _yaml

    values = _yaml.safe_load((HELM_DIR / "values.yaml").read_text())
    assert values["image"]["repository"]
    assert values["service"]["port"] == 8000
    # Security: non-root
    sc = values["securityContext"]
    assert sc["runAsNonRoot"] is True
    assert sc["allowPrivilegeEscalation"] is False
    # HPA enabled by default
    assert values["autoscaling"]["enabled"] is True


def test_helm_required_templates_present():
    """Core Helm templates must all be there."""
    expected = {
        "_helpers.tpl",
        "deployment.yaml",
        "service.yaml",
        "configmap.yaml",
        "hpa.yaml",
        "serviceaccount.yaml",
        "ingress.yaml",
    }
    actual = {p.name for p in (HELM_DIR / "templates").iterdir()}
    assert expected.issubset(actual), f"Missing: {expected - actual}"


def test_deployment_template_includes_health_probes():
    content = (HELM_DIR / "templates" / "deployment.yaml").read_text()
    assert "livenessProbe" in content
    assert "readinessProbe" in content
    assert "/health" in content


def test_deployment_template_uses_security_context():
    content = (HELM_DIR / "templates" / "deployment.yaml").read_text()
    assert "securityContext" in content
    assert "podSecurityContext" in content


def test_deployment_template_mounts_audit_logs():
    """Audit logs need persistence, even via emptyDir."""
    content = (HELM_DIR / "templates" / "deployment.yaml").read_text()
    assert "audit-logs" in content
    assert "/var/log/largestack" in content


def test_helm_helpers_define_required_macros():
    content = (HELM_DIR / "templates" / "_helpers.tpl").read_text()
    assert 'define "largestack.labels"' in content
    assert 'define "largestack.selectorLabels"' in content
    assert 'define "largestack.serviceAccountName"' in content
    assert 'define "largestack.fullname"' in content


def test_helm_readme_exists():
    readme = HELM_DIR / "README.md"
    assert readme.exists()
    content = readme.read_text()
    assert "helm install" in content


def test_hpa_template_has_metrics():
    """HPA must scale on CPU + memory."""
    content = (HELM_DIR / "templates" / "hpa.yaml").read_text()
    assert "cpu" in content
    assert "memory" in content
    assert "averageUtilization" in content
