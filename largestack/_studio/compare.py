"""Studio side-by-side comparison (v0.14.0).

Closes Tier A #6 from the v0.12 audit. Renders two ``StudioBuilder``
payloads as a single HTML with overlay deltas:

- Nodes added / removed / changed between runs
- Audit events that diverge
- Memory state diffs
- Compliance markers added or removed

Use case: "v0.12 vs main: KYC pass-rate dropped — show me what changed
in the agent graph"::

    from largestack._studio import StudioBuilder
    from largestack._studio.compare import render_comparison_html

    a = StudioBuilder(title="KYC v0.12")
    a.add_node("intake"); a.add_node("verify"); a.add_edge("intake", "verify")
    b = StudioBuilder(title="KYC main")
    b.add_node("intake"); b.add_node("verify"); b.add_node("approve")
    b.add_edge("intake", "verify"); b.add_edge("verify", "approve")

    html = render_comparison_html(a, b, label_a="v0.12", label_b="main")
    Path("compare.html").write_text(html)
"""

from __future__ import annotations
import html as _html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StudioDiff:
    """Computed delta between two ``StudioBuilder`` payloads."""

    nodes_added: list[str] = field(default_factory=list)
    nodes_removed: list[str] = field(default_factory=list)
    nodes_changed: list[dict[str, Any]] = field(default_factory=list)
    edges_added: list[tuple[str, str]] = field(default_factory=list)
    edges_removed: list[tuple[str, str]] = field(default_factory=list)
    audit_only_a: list[dict[str, Any]] = field(default_factory=list)
    audit_only_b: list[dict[str, Any]] = field(default_factory=list)
    compliance_added: list[str] = field(default_factory=list)
    compliance_removed: list[str] = field(default_factory=list)
    memory_diff: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes_added": self.nodes_added,
            "nodes_removed": self.nodes_removed,
            "nodes_changed": self.nodes_changed,
            "edges_added": [list(e) for e in self.edges_added],
            "edges_removed": [list(e) for e in self.edges_removed],
            "audit_only_a": self.audit_only_a,
            "audit_only_b": self.audit_only_b,
            "compliance_added": self.compliance_added,
            "compliance_removed": self.compliance_removed,
            "memory_diff": self.memory_diff,
        }

    @property
    def has_changes(self) -> bool:
        return any(
            [
                self.nodes_added,
                self.nodes_removed,
                self.nodes_changed,
                self.edges_added,
                self.edges_removed,
                self.audit_only_a,
                self.audit_only_b,
                self.compliance_added,
                self.compliance_removed,
                self.memory_diff,
            ]
        )


def _builder_to_dict(builder) -> dict[str, Any]:
    """Extract a dict view of a StudioBuilder for comparison."""
    # StudioBuilder uses private attributes _nodes, _edges, _audit, _memory, _compliance
    raw_nodes = getattr(builder, "_nodes", None) or getattr(builder, "nodes", None) or []
    raw_edges = getattr(builder, "_edges", None) or getattr(builder, "edges", None) or []
    raw_audit = getattr(builder, "_audit", None) or getattr(builder, "audit_events", None) or []
    raw_memory = getattr(builder, "_memory", None) or getattr(builder, "memory_snapshot", None)
    raw_compliance = (
        getattr(builder, "_compliance", None) or getattr(builder, "compliance", None) or []
    )

    nodes: dict[str, dict[str, Any]] = {}
    for n in raw_nodes:
        if isinstance(n, dict):
            nid = n.get("id")
            if nid:
                nodes[nid] = {
                    "id": nid,
                    "kind": n.get("kind"),
                    "label": n.get("label"),
                }
        else:
            nid = getattr(n, "id", None)
            if nid:
                nodes[nid] = {
                    "id": nid,
                    "kind": getattr(n, "kind", None),
                    "label": getattr(n, "label", None),
                }

    edges: list[tuple[str, str]] = []
    for e in raw_edges:
        if isinstance(e, dict):
            edges.append(
                (
                    e.get("source") or e.get("from") or "",
                    e.get("target") or e.get("to") or "",
                )
            )
        else:
            edges.append(
                (
                    getattr(e, "source", "") or getattr(e, "from_id", "") or getattr(e, "src", ""),
                    getattr(e, "target", "") or getattr(e, "to_id", "") or getattr(e, "dst", ""),
                )
            )

    audit = []
    for ev in raw_audit:
        if isinstance(ev, dict):
            audit.append(
                {
                    "event": ev.get("event") or ev.get("action", ""),
                    "agent": ev.get("agent", ""),
                    "payload": ev.get("payload") or ev.get("data", {}),
                }
            )
        else:
            audit.append(
                {
                    "event": getattr(ev, "event", "") or getattr(ev, "action", ""),
                    "agent": getattr(ev, "agent", ""),
                    "payload": getattr(ev, "payload", None) or getattr(ev, "data", {}),
                }
            )

    compliance = []
    for c in raw_compliance:
        if isinstance(c, dict):
            compliance.append(f"{c.get('name', '?')}/{c.get('section', '')}".rstrip("/"))
        else:
            compliance.append(f"{getattr(c, 'name', '?')}/{getattr(c, 'section', '')}".rstrip("/"))

    memory_dict: dict[str, Any] = {}
    if raw_memory is not None:
        if isinstance(raw_memory, dict):
            memory_dict = raw_memory
        else:
            # MemorySnapshot dataclass
            for k in (
                "tenant_id",
                "user_id",
                "core_count",
                "recall_count",
                "archival_count",
                "core_block_preview",
            ):
                if hasattr(raw_memory, k):
                    memory_dict[k] = getattr(raw_memory, k)

    title = getattr(builder, "title", "") or ""

    return {
        "title": title,
        "nodes": nodes,
        "edges": edges,
        "audit_events": audit,
        "compliance": compliance,
        "memory": memory_dict,
    }


def compute_diff(a, b) -> StudioDiff:
    """Compute the diff between two StudioBuilder payloads."""
    da = _builder_to_dict(a)
    db = _builder_to_dict(b)

    a_node_ids = set(da["nodes"].keys())
    b_node_ids = set(db["nodes"].keys())

    diff = StudioDiff()
    diff.nodes_added = sorted(b_node_ids - a_node_ids)
    diff.nodes_removed = sorted(a_node_ids - b_node_ids)

    # Changed: same id, different label/kind
    for nid in sorted(a_node_ids & b_node_ids):
        if da["nodes"][nid] != db["nodes"][nid]:
            diff.nodes_changed.append(
                {
                    "id": nid,
                    "before": da["nodes"][nid],
                    "after": db["nodes"][nid],
                }
            )

    a_edges = set(da["edges"])
    b_edges = set(db["edges"])
    diff.edges_added = sorted(b_edges - a_edges)
    diff.edges_removed = sorted(a_edges - b_edges)

    # Audit events: list-equality based diff
    a_audit_keys = {json.dumps(e, sort_keys=True) for e in da["audit_events"]}
    b_audit_keys = {json.dumps(e, sort_keys=True) for e in db["audit_events"]}
    only_a_keys = a_audit_keys - b_audit_keys
    only_b_keys = b_audit_keys - a_audit_keys
    diff.audit_only_a = [
        e for e in da["audit_events"] if json.dumps(e, sort_keys=True) in only_a_keys
    ]
    diff.audit_only_b = [
        e for e in db["audit_events"] if json.dumps(e, sort_keys=True) in only_b_keys
    ]

    a_comp = set(da["compliance"])
    b_comp = set(db["compliance"])
    diff.compliance_added = sorted(b_comp - a_comp)
    diff.compliance_removed = sorted(a_comp - b_comp)

    # Memory: shallow key diff
    if da["memory"] != db["memory"]:
        all_keys = set(da["memory"].keys()) | set(db["memory"].keys())
        diff.memory_diff = {
            k: {"before": da["memory"].get(k), "after": db["memory"].get(k)}
            for k in sorted(all_keys)
            if da["memory"].get(k) != db["memory"].get(k)
        }

    return diff


def render_comparison_html(
    a,
    b,
    *,
    label_a: str = "A",
    label_b: str = "B",
    title: str = "LARGESTACK Studio — Run Comparison",
) -> str:
    """Render side-by-side HTML with overlay deltas."""
    diff = compute_diff(a, b)
    payload = {
        "label_a": label_a,
        "label_b": label_b,
        "a": _builder_to_dict(a),
        "b": _builder_to_dict(b),
        "diff": diff.to_dict(),
    }
    payload_json = (
        json.dumps(payload, indent=2).replace("</", "<\\/")  # XSS safety inside <script>
    )
    safe_title = _html.escape(title)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_title}</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0; font-family: ui-sans-serif, system-ui, -apple-system; margin:0; padding:24px; }}
  h1 {{ color:#f8fafc; font-size:20px; margin:0 0 16px; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:10px; font-size:12px; margin-right:6px; }}
  .badge-a {{ background:#1e3a5f; color:#7dd3fc; }}
  .badge-b {{ background:#3a1f5f; color:#c4b5fd; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .panel {{ background:#1e293b; border-radius:8px; padding:16px; min-height:300px; }}
  .panel h2 {{ font-size:14px; color:#94a3b8; margin:0 0 12px; }}
  .node {{ background:#334155; border:1px solid #475569; border-radius:6px; padding:6px 10px; margin:4px; display:inline-block; font-size:13px; }}
  .node-added {{ border-color:#10b981; background:#064e3b; }}
  .node-removed {{ border-color:#ef4444; background:#7f1d1d; }}
  .node-changed {{ border-color:#f59e0b; background:#78350f; }}
  .diff-section {{ margin-top:24px; padding:16px; background:#1e293b; border-radius:8px; border-left:4px solid #f59e0b; }}
  .diff-section h2 {{ color:#fbbf24; font-size:14px; margin:0 0 8px; }}
  .diff-section ul {{ margin:0; padding-left:20px; font-size:13px; line-height:1.6; }}
  .added {{ color:#10b981; }}
  .removed {{ color:#ef4444; }}
  .changed {{ color:#f59e0b; }}
  .empty {{ color:#64748b; font-style:italic; }}
  .compliance-tag {{ display:inline-block; background:#0c4a6e; color:#7dd3fc; padding:2px 8px; border-radius:4px; font-size:11px; margin:2px; }}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<div>
  <span class="badge badge-a">{_html.escape(label_a)}</span>
  <span class="badge badge-b">{_html.escape(label_b)}</span>
</div>

<div class="grid" style="margin-top:16px">
  <div class="panel">
    <h2>{_html.escape(label_a)}: {_html.escape(payload["a"]["title"] or "untitled")}</h2>
    <div id="panel-a"></div>
  </div>
  <div class="panel">
    <h2>{_html.escape(label_b)}: {_html.escape(payload["b"]["title"] or "untitled")}</h2>
    <div id="panel-b"></div>
  </div>
</div>

<div id="diff-output"></div>

<script>
const PAYLOAD = {payload_json};

function renderNodes(elId, side) {{
  const el = document.getElementById(elId);
  const nodes = PAYLOAD[side].nodes;
  const diff = PAYLOAD.diff;
  const ids = Object.keys(nodes);
  if (ids.length === 0) {{
    el.innerHTML = '<div class="empty">no nodes</div>';
    return;
  }}
  el.innerHTML = ids.map(id => {{
    let cls = 'node';
    if (side === 'b' && diff.nodes_added.includes(id)) cls += ' node-added';
    if (side === 'a' && diff.nodes_removed.includes(id)) cls += ' node-removed';
    if (diff.nodes_changed.some(c => c.id === id)) cls += ' node-changed';
    const label = nodes[id].label || id;
    return `<div class="${{cls}}">${{label}}</div>`;
  }}).join('');
}}

function renderDiff() {{
  const el = document.getElementById('diff-output');
  const d = PAYLOAD.diff;
  let html = '';

  if (d.nodes_added.length || d.nodes_removed.length || d.nodes_changed.length) {{
    html += '<div class="diff-section"><h2>Node changes</h2><ul>';
    d.nodes_added.forEach(n => html += `<li class="added">+ ${{n}} (added in ${{PAYLOAD.label_b}})</li>`);
    d.nodes_removed.forEach(n => html += `<li class="removed">− ${{n}} (only in ${{PAYLOAD.label_a}})</li>`);
    d.nodes_changed.forEach(c => html += `<li class="changed">~ ${{c.id}} (changed)</li>`);
    html += '</ul></div>';
  }}

  if (d.edges_added.length || d.edges_removed.length) {{
    html += '<div class="diff-section"><h2>Edge changes</h2><ul>';
    d.edges_added.forEach(e => html += `<li class="added">+ ${{e[0]}} → ${{e[1]}}</li>`);
    d.edges_removed.forEach(e => html += `<li class="removed">− ${{e[0]}} → ${{e[1]}}</li>`);
    html += '</ul></div>';
  }}

  if (d.compliance_added.length || d.compliance_removed.length) {{
    html += '<div class="diff-section"><h2>Compliance markers</h2>';
    d.compliance_added.forEach(c => html += `<span class="compliance-tag added">+ ${{c}}</span>`);
    d.compliance_removed.forEach(c => html += `<span class="compliance-tag removed">− ${{c}}</span>`);
    html += '</div>';
  }}

  if (d.audit_only_a.length || d.audit_only_b.length) {{
    html += '<div class="diff-section"><h2>Audit divergence</h2><ul>';
    d.audit_only_a.forEach(e => html += `<li class="removed">only in ${{PAYLOAD.label_a}}: ${{e.event || JSON.stringify(e)}}</li>`);
    d.audit_only_b.forEach(e => html += `<li class="added">only in ${{PAYLOAD.label_b}}: ${{e.event || JSON.stringify(e)}}</li>`);
    html += '</ul></div>';
  }}

  if (Object.keys(d.memory_diff).length) {{
    html += '<div class="diff-section"><h2>Memory state diff</h2><ul>';
    Object.entries(d.memory_diff).forEach(([k, v]) => {{
      html += `<li class="changed">~ ${{k}}: ${{JSON.stringify(v.before)}} → ${{JSON.stringify(v.after)}}</li>`;
    }});
    html += '</ul></div>';
  }}

  if (!html) {{
    html = '<div class="diff-section"><h2>No differences</h2><p class="empty">The two runs are identical.</p></div>';
  }}

  el.innerHTML = html;
}}

renderNodes('panel-a', 'a');
renderNodes('panel-b', 'b');
renderDiff();
</script>
</body>
</html>
"""


def export_comparison(
    a,
    b,
    output_path: str | Path,
    *,
    label_a: str = "A",
    label_b: str = "B",
    title: str = "LARGESTACK Studio — Run Comparison",
) -> Path:
    """Render and write comparison HTML to a file."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        render_comparison_html(a, b, label_a=label_a, label_b=label_b, title=title),
        encoding="utf-8",
    )
    return p


__all__ = [
    "StudioDiff",
    "compute_diff",
    "render_comparison_html",
    "export_comparison",
]
