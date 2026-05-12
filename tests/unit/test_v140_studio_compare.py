"""v0.14.0: Tests for Studio side-by-side comparison."""
from __future__ import annotations

import pytest


def _build_a():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec, ComplianceMarker
    a = StudioBuilder(title="KYC v0.12")
    a.add_node(NodeSpec(id="intake", label="Intake"))
    a.add_node(NodeSpec(id="verify", label="Verify"))
    a.add_edge(EdgeSpec(source="intake", target="verify"))
    a.add_audit_event(agent="kyc", event="pan_verify", payload={"x": 1})
    a.add_compliance(ComplianceMarker(name="DPDP_Act_2023", section="Section 6"))
    return a


def _build_b():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec, ComplianceMarker
    b = StudioBuilder(title="KYC main")
    b.add_node(NodeSpec(id="intake", label="Intake"))
    b.add_node(NodeSpec(id="verify", label="Verify (v2)"))  # changed label
    b.add_node(NodeSpec(id="approve", label="Approve"))     # added
    b.add_edge(EdgeSpec(source="intake", target="verify"))
    b.add_edge(EdgeSpec(source="verify", target="approve"))  # added edge
    b.add_audit_event(agent="kyc", event="pan_verify", payload={"x": 1})
    b.add_audit_event(agent="kyc", event="approve_loan", payload={"y": 2})
    b.add_compliance(ComplianceMarker(name="DPDP_Act_2023", section="Section 6"))
    b.add_compliance(ComplianceMarker(name="RBI_MD_NBFC_D", section="NBFC"))
    return b


def test_compute_diff_finds_added_node():
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    assert "approve" in diff.nodes_added


def test_compute_diff_finds_changed_node():
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    changed_ids = [c["id"] for c in diff.nodes_changed]
    assert "verify" in changed_ids


def test_compute_diff_finds_added_edge():
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    assert ("verify", "approve") in diff.edges_added


def test_compute_diff_finds_added_compliance():
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    assert any("RBI" in c for c in diff.compliance_added)


def test_compute_diff_finds_audit_divergence():
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    assert any(e["event"] == "approve_loan" for e in diff.audit_only_b)


def test_compute_diff_no_changes_for_identical():
    from largestack._studio.compare import compute_diff
    a = _build_a()
    a2 = _build_a()
    diff = compute_diff(a, a2)
    assert not diff.has_changes


def test_render_html_contains_both_labels():
    from largestack._studio.compare import render_comparison_html
    html = render_comparison_html(
        _build_a(), _build_b(),
        label_a="v0.12", label_b="main",
    )
    assert "v0.12" in html
    assert "main" in html
    assert "<!doctype html>" in html.lower() or "<!DOCTYPE html>" in html


def test_render_html_xss_safe_for_titles():
    from largestack._studio import StudioBuilder
    from largestack._studio.compare import render_comparison_html
    bad = StudioBuilder(title="<script>alert('xss')</script>")
    safe = StudioBuilder(title="ok")
    html = render_comparison_html(bad, safe)
    # XSS via title in <title> / <h1>: must be HTML-escaped
    assert "&lt;script&gt;" in html
    # XSS via embedded JSON: closing </script> must be escaped
    assert "</script>alert" not in html  # the breakout
    # Valid escaped form should be present in payload
    assert "<\\/script>" in html or "<\\/" in html


def test_export_writes_file(tmp_path):
    from largestack._studio.compare import export_comparison
    out = tmp_path / "cmp.html"
    written = export_comparison(_build_a(), _build_b(), out)
    assert written.exists()
    assert written.read_text(encoding="utf-8").startswith("<!doctype")


def test_diff_to_dict_serializable():
    """The diff must be JSON-serializable for embedding in HTML."""
    import json
    from largestack._studio.compare import compute_diff
    diff = compute_diff(_build_a(), _build_b())
    json.dumps(diff.to_dict())  # must not raise
