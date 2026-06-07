"""v0.12.0: Tests for LARGESTACK Studio v0 — single-HTML graph visualizer."""

from __future__ import annotations

import json
import time

import pytest


def test_node_spec_defaults():
    from largestack._studio import NodeSpec

    n = NodeSpec(id="x", label="X")
    assert n.kind == "agent"
    assert n.metadata == {}


def test_edge_spec_defaults():
    from largestack._studio import EdgeSpec

    e = EdgeSpec(source="a", target="b")
    assert e.label == ""
    assert e.condition == ""


def test_builder_add_node_and_edge():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec

    b = StudioBuilder(title="t")
    b.add_node(NodeSpec(id="a", label="A", kind="start"))
    b.add_node(NodeSpec(id="b", label="B", kind="agent"))
    b.add_edge(EdgeSpec(source="a", target="b"))
    payload = b.build_payload()
    assert len(payload["nodes"]) == 2
    assert len(payload["edges"]) == 1
    assert payload["nodes"][0]["kind"] == "start"


def test_builder_rejects_duplicate_node_id():
    from largestack._studio import StudioBuilder, NodeSpec

    b = StudioBuilder()
    b.add_node(NodeSpec(id="a", label="A"))
    with pytest.raises(ValueError, match="duplicate"):
        b.add_node(NodeSpec(id="a", label="A2"))


def test_builder_rejects_edge_with_unknown_source():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec

    b = StudioBuilder()
    b.add_node(NodeSpec(id="a", label="A"))
    with pytest.raises(ValueError, match="source"):
        b.add_edge(EdgeSpec(source="nope", target="a"))


def test_builder_rejects_edge_with_unknown_target():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec

    b = StudioBuilder()
    b.add_node(NodeSpec(id="a", label="A"))
    with pytest.raises(ValueError, match="target"):
        b.add_edge(EdgeSpec(source="a", target="nope"))


def test_builder_audit_events():
    from largestack._studio import StudioBuilder

    b = StudioBuilder()
    b.add_audit_event(
        agent="kyc",
        event="pan_verify",
        payload={"pan": "AAACR1234C"},
        duration_ms=234.0,
    )
    payload = b.build_payload()
    assert len(payload["audit"]) == 1
    assert payload["audit"][0]["agent"] == "kyc"
    assert payload["audit"][0]["payload"]["pan"] == "AAACR1234C"


def test_builder_memory_snapshot():
    from largestack._studio import StudioBuilder, MemorySnapshot

    b = StudioBuilder()
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id="t1",
            user_id="u1",
            core_count=3,
            recall_count=10,
            archival_count=22,
            core_block_preview="persona: helpful",
        )
    )
    payload = b.build_payload()
    assert payload["memory"]["core_count"] == 3
    assert payload["memory"]["recall_count"] == 10


def test_builder_compliance_markers():
    from largestack._studio import StudioBuilder, ComplianceMarker

    b = StudioBuilder()
    b.add_compliance(
        ComplianceMarker(
            name="DPDP_Act_2023",
            section="Section 6",
            notes="explicit consent required",
        )
    )
    payload = b.build_payload()
    assert len(payload["compliance"]) == 1
    assert payload["compliance"][0]["name"] == "DPDP_Act_2023"


def test_render_html_is_valid_self_contained_document():
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec

    b = StudioBuilder(title="My Agent", description="An agent")
    b.add_node(NodeSpec(id="start", label="Start", kind="start"))
    b.add_node(NodeSpec(id="end", label="End", kind="end"))
    b.add_edge(EdgeSpec(source="start", target="end"))

    html = b.render_html()
    # Basic HTML structure
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html
    # Title escaped + present
    assert "My Agent" in html
    # Embedded JSON
    assert '"nodes"' in html
    assert "Start" in html
    # Self-contained: no external src/href
    assert 'src="http' not in html.lower()
    # Inline script
    assert "<script>" in html


def test_render_html_escapes_xss_in_title():
    from largestack._studio import StudioBuilder

    b = StudioBuilder(title="<script>alert(1)</script>")
    html = b.render_html()
    # Title should be escaped, not raw
    assert "<script>alert(1)</script>" not in html.split("{{PAYLOAD_JSON}}")[0]
    assert "&lt;script&gt;" in html


def test_render_html_escapes_closing_script_in_payload():
    """Embedded JSON containing </ must be escaped to prevent
    breaking out of the <script> block."""
    from largestack._studio import StudioBuilder, NodeSpec

    b = StudioBuilder()
    b.add_node(
        NodeSpec(
            id="x",
            label="</script><script>alert(1)</script>",
        )
    )
    html = b.render_html()
    # The </script> in the payload must be escaped
    assert "</script><script>alert" not in html


def test_export_writes_file(tmp_path):
    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec

    b = StudioBuilder(title="Test")
    b.add_node(NodeSpec(id="a", label="A"))
    out = tmp_path / "studio.html"
    result = b.export(out)
    assert result.exists()
    assert result == out
    content = out.read_text()
    assert "<!DOCTYPE html>" in content
    assert "Test" in content


def test_export_creates_parent_dirs(tmp_path):
    from largestack._studio import StudioBuilder

    b = StudioBuilder()
    out = tmp_path / "deep" / "nested" / "studio.html"
    b.export(out)
    assert out.exists()


@pytest.mark.asyncio
async def test_from_memory_manager_helper():
    from largestack._memory.long_term import LongTermMemoryManager
    from largestack._studio import from_memory_manager

    mgr = LongTermMemoryManager(tenant_id="t1", user_id="u1")
    await mgr.add_core("persona test", tag="persona")
    await mgr.add_recall("a recall fact")
    await mgr.add_archival("an archival fact")

    snap = await from_memory_manager(mgr)
    assert snap.tenant_id == "t1"
    assert snap.user_id == "u1"
    assert snap.core_count == 1
    assert snap.recall_count == 1
    assert snap.archival_count == 1
    assert "persona test" in snap.core_block_preview


def test_from_audit_log_records_helper():
    from largestack._studio import from_audit_log_records

    records = [
        {
            "timestamp": 1000.0,
            "agent": "kyc",
            "event": "verify",
            "payload": {"pan": "X"},
            "tenant_id": "t1",
            "user_id": "u1",
            "duration_ms": 100.0,
        },
        {
            "timestamp": 1001.0,
            "agent": "router",
            "action": "route_to_kyc",
            "data": {"reason": "kyc-needed"},
        },
    ]
    events = from_audit_log_records(records)
    assert len(events) == 2
    assert events[0].agent == "kyc"
    assert events[0].payload == {"pan": "X"}
    # Tolerant key mapping: action → event, data → payload
    assert events[1].event == "route_to_kyc"
    assert events[1].payload == {"reason": "kyc-needed"}


def test_payload_includes_generated_at():
    from largestack._studio import StudioBuilder

    b = StudioBuilder()
    payload = b.build_payload()
    assert "generated_at" in payload
    assert payload["generated_at"] > 0


def test_payload_serializes_to_valid_json():
    from largestack._studio import (
        StudioBuilder,
        NodeSpec,
        EdgeSpec,
        MemorySnapshot,
        ComplianceMarker,
    )

    b = StudioBuilder(title="Full Test")
    b.add_node(NodeSpec(id="a", label="A"))
    b.add_node(NodeSpec(id="b", label="B"))
    b.add_edge(EdgeSpec(source="a", target="b", label="next"))
    b.add_audit_event(agent="x", event="y", payload={"k": 1})
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id="t1",
            user_id="u1",
            core_count=1,
        )
    )
    b.add_compliance(ComplianceMarker(name="DPDP_Act_2023"))

    # Must round-trip through JSON
    payload = b.build_payload()
    s = json.dumps(payload)
    rebuilt = json.loads(s)
    assert rebuilt["title"] == "Full Test"
    assert len(rebuilt["nodes"]) == 2
    assert rebuilt["audit"][0]["payload"]["k"] == 1
