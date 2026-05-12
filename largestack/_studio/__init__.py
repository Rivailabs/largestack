"""LARGESTACK Studio v0 — single-HTML graph + audit visualizer (v0.12.0).

Closes (partially) the LangGraph Studio gap. This is a **lightweight,
local, single-file** alternative — generates one self-contained HTML
file with embedded JSON data + vanilla JS. No build step, no server,
no LangSmith account required.

What it shows:
- Agent graph topology (nodes, edges)
- Audit log timeline (per-step trace from a LARGESTACK run)
- Memory state snapshot (if a ``LongTermMemoryManager`` is provided)
- Indian compliance markers (DPDP / RBI / PMLA tags from agent.yaml)

What it does NOT do (vs LangGraph Studio):
- Time-travel state editing → use LARGESTACK checkpoints directly
- Live hot-reload → re-run ``studio.export()`` after code changes

For richer features pair with LangGraph Studio (compatible) or use
LARGESTACK Studio v1 (planned).

Usage::

    from largestack._studio import StudioBuilder, NodeSpec, EdgeSpec
    builder = StudioBuilder(title="My KYC Agent")
    builder.add_node(NodeSpec(id="start", label="Start", kind="start"))
    builder.add_node(NodeSpec(id="kyc", label="KYC Verify", kind="agent"))
    builder.add_edge(EdgeSpec(source="start", target="kyc"))
    builder.add_audit_event(
        timestamp=time.time(), agent="kyc",
        event="pan_verify", payload={"pan": "AAACR1234C"},
    )
    builder.export("/tmp/studio.html")
"""
from __future__ import annotations
import html
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger("largestack.studio")


# -------------------- Domain types --------------------

NodeKind = Literal[
    "start", "agent", "tool", "decision", "end", "checkpoint",
]


@dataclass
class NodeSpec:
    """A node in the agent graph."""
    id: str
    label: str
    kind: NodeKind = "agent"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeSpec:
    """An edge between two nodes."""
    source: str
    target: str
    label: str = ""
    condition: str = ""


@dataclass
class AuditEvent:
    """One entry on the audit timeline."""
    timestamp: float
    agent: str
    event: str
    payload: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    user_id: str = ""
    duration_ms: float = 0.0


@dataclass
class MemorySnapshot:
    """Snapshot of memory state at the end of a run."""
    tenant_id: str
    user_id: str
    core_count: int = 0
    recall_count: int = 0
    archival_count: int = 0
    core_block_preview: str = ""


@dataclass
class ComplianceMarker:
    """Indian compliance marker from agent.yaml."""
    name: str  # "DPDP_Act_2023", "RBI_PA_PG_2024", "PMLA_2002"
    section: str = ""
    notes: str = ""


# -------------------- Builder --------------------

class StudioBuilder:
    """Builder for a single-HTML Studio export."""

    def __init__(
        self,
        *,
        title: str = "LARGESTACK Agent",
        description: str = "",
    ):
        self.title = title
        self.description = description
        self._nodes: list[NodeSpec] = []
        self._edges: list[EdgeSpec] = []
        self._audit: list[AuditEvent] = []
        self._memory: MemorySnapshot | None = None
        self._compliance: list[ComplianceMarker] = []

    def add_node(self, node: NodeSpec) -> None:
        if any(n.id == node.id for n in self._nodes):
            raise ValueError(f"duplicate node id: {node.id}")
        self._nodes.append(node)

    def add_edge(self, edge: EdgeSpec) -> None:
        node_ids = {n.id for n in self._nodes}
        if edge.source not in node_ids:
            raise ValueError(f"edge source not in graph: {edge.source}")
        if edge.target not in node_ids:
            raise ValueError(f"edge target not in graph: {edge.target}")
        self._edges.append(edge)

    def add_audit_event(
        self,
        *,
        timestamp: float | None = None,
        agent: str = "",
        event: str = "",
        payload: dict[str, Any] | None = None,
        tenant_id: str = "",
        user_id: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        self._audit.append(AuditEvent(
            timestamp=timestamp if timestamp is not None else time.time(),
            agent=agent, event=event,
            payload=payload or {},
            tenant_id=tenant_id, user_id=user_id,
            duration_ms=duration_ms,
        ))

    def set_memory_snapshot(self, snap: MemorySnapshot) -> None:
        self._memory = snap

    def add_compliance(self, marker: ComplianceMarker) -> None:
        self._compliance.append(marker)

    # -------------------- Build the JSON payload --------------------

    def build_payload(self) -> dict[str, Any]:
        """Build the JSON payload that will be embedded in the HTML."""
        return {
            "title": self.title,
            "description": self.description,
            "nodes": [asdict(n) for n in self._nodes],
            "edges": [asdict(e) for e in self._edges],
            "audit": [asdict(a) for a in self._audit],
            "memory": asdict(self._memory) if self._memory else None,
            "compliance": [asdict(c) for c in self._compliance],
            "generated_at": time.time(),
        }

    # -------------------- Render HTML --------------------

    def render_html(self) -> str:
        payload = self.build_payload()
        # JSON safe-encode for embedding in <script>
        json_data = json.dumps(payload, indent=2)
        # HTML-escape the title in the document (json_data inside script
        # tag is safe as long as we escape </ inside it)
        json_data = json_data.replace("</", "<\\/")
        title_html = html.escape(self.title)
        return _STUDIO_TEMPLATE.replace(
            "{{TITLE}}", title_html,
        ).replace(
            "{{PAYLOAD_JSON}}", json_data,
        )

    def export(self, path: str | Path) -> Path:
        """Write the HTML to ``path``. Returns the resolved Path."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.render_html(), encoding="utf-8")
        log.info(f"LARGESTACK Studio exported to {out}")
        return out


# -------------------- Connector helpers (auto-build from LARGESTACK) --------------------

async def from_memory_manager(manager) -> MemorySnapshot:
    """Build a ``MemorySnapshot`` from a ``LongTermMemoryManager``."""
    stats = await manager.stats()
    core_block = await manager.get_core_block()
    return MemorySnapshot(
        tenant_id=manager.tenant_id,
        user_id=manager.user_id,
        core_count=stats.by_tier.get("core", 0),
        recall_count=stats.by_tier.get("recall", 0),
        archival_count=stats.by_tier.get("archival", 0),
        core_block_preview=core_block[:500],
    )


def from_audit_log_records(records: list[dict[str, Any]]) -> list[AuditEvent]:
    """Convert LARGESTACK audit-log dict records → AuditEvent list."""
    events = []
    for r in records:
        events.append(AuditEvent(
            timestamp=r.get("timestamp", time.time()),
            agent=r.get("agent", ""),
            event=r.get("event", r.get("action", "")),
            payload=r.get("payload", r.get("data", {})),
            tenant_id=r.get("tenant_id", ""),
            user_id=r.get("user_id", ""),
            duration_ms=r.get("duration_ms", 0.0),
        ))
    return events


# -------------------- HTML template --------------------

_STUDIO_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}} — LARGESTACK Studio</title>
<style>
  :root[data-theme="dark"] {
    --bg: #0b1220;
    --surface: #131c2e;
    --surface-2: #1a2436;
    --surface-3: #0f1828;
    --border: #243149;
    --text: #e6edf7;
    --text-2: #9aa7c0;
    --muted: #6b7891;
    --accent: #5eead4;
    --accent-2: #f59e0b;
    --green: #22c55e;
    --red: #ef4444;
    --blue: #3b82f6;
    --purple: #a78bfa;
    --shadow: 0 1px 0 rgba(255,255,255,0.04);
  }
  :root[data-theme="light"] {
    --bg: #f8fafc;
    --surface: #ffffff;
    --surface-2: #f1f5f9;
    --surface-3: #e2e8f0;
    --border: #cbd5e1;
    --text: #0f172a;
    --text-2: #475569;
    --muted: #64748b;
    --accent: #0d9488;
    --accent-2: #b45309;
    --green: #15803d;
    --red: #b91c1c;
    --blue: #1d4ed8;
    --purple: #7c3aed;
    --shadow: 0 1px 2px rgba(15,23,42,0.04);
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body {
    font-family: -apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 24px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    position: sticky; top: 0; z-index: 10;
  }
  .topbar .brand {
    display: flex; align-items: center; gap: 10px;
  }
  .topbar h1 {
    font-size: 15px; font-weight: 600; margin: 0;
  }
  .topbar .pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 12px;
    background: var(--surface-2);
    color: var(--accent);
    font-size: 11px; font-weight: 500;
    border: 1px solid var(--border);
  }
  .topbar .pill .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--accent);
  }
  .topbar .meta {
    color: var(--text-2); font-size: 11px;
  }
  .topbar button {
    background: var(--surface-2);
    color: var(--text-2);
    border: 1px solid var(--border);
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 11px;
    cursor: pointer;
    margin-left: 6px;
    font-family: inherit;
  }
  .topbar button:hover { color: var(--text); }

  /* KPI strip */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    padding: 16px 24px 0;
  }
  .kpi {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px 16px;
    box-shadow: var(--shadow);
  }
  .kpi .label {
    color: var(--text-2);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 500;
  }
  .kpi .value {
    font-size: 22px; font-weight: 600;
    margin-top: 4px;
    font-variant-numeric: tabular-nums;
  }
  .kpi .sub {
    font-size: 11px; color: var(--muted);
    margin-top: 2px;
  }
  .kpi.ok .value { color: var(--green); }
  .kpi.warn .value { color: var(--accent-2); }
  .kpi.bad .value { color: var(--red); }

  main {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 360px;
    gap: 16px;
    padding: 16px 24px 24px;
  }
  .col-stack > section + section { margin-top: 16px; }

  section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: var(--shadow);
  }
  section header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
  }
  section header h2 {
    margin: 0; font-size: 12px; font-weight: 600;
    color: var(--text-2);
    text-transform: uppercase; letter-spacing: 0.06em;
  }
  section header .actions {
    display: flex; gap: 4px;
  }
  section header .actions button {
    background: transparent; border: 1px solid var(--border);
    color: var(--muted); cursor: pointer;
    padding: 3px 8px; border-radius: 5px;
    font-size: 11px; font-family: inherit;
  }
  section header .actions button:hover { color: var(--text); }
  section .body { padding: 14px 16px; }

  /* Graph */
  #graph .body { padding: 8px; }
  #graph svg {
    width: 100%; height: 720px;
    background: var(--surface-3);
    border-radius: 6px;
    display: block;
  }
  .node-rect {
    fill: var(--surface-2);
    stroke: var(--blue);
    stroke-width: 1.5;
  }
  .node-rect.start  { stroke: var(--green); }
  .node-rect.end    { stroke: var(--red); }
  .node-rect.tool   { stroke: var(--accent-2); }
  .node-rect.decision {
    stroke: var(--purple); stroke-dasharray: 4 3;
  }
  .node-rect.checkpoint { stroke: var(--muted); }
  .node-text { fill: var(--text); font-size: 14px; font-weight: 500; }
  .node-kind { fill: var(--text-2); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; }
  .edge-line { stroke: var(--muted); stroke-width: 1.5; fill: none; opacity: 0.7; }
  .edge-arrow { fill: var(--muted); }
  .edge-label {
    fill: var(--text-2); font-size: 10px;
    paint-order: stroke; stroke: var(--surface-3); stroke-width: 3px;
  }

  .legend {
    display: flex; gap: 12px; flex-wrap: wrap;
    padding: 8px 12px 0;
    font-size: 11px; color: var(--text-2);
  }
  .legend .item {
    display: inline-flex; align-items: center; gap: 5px;
  }
  .legend .swatch {
    width: 10px; height: 10px; border-radius: 3px;
    border: 1.5px solid;
  }

  /* Audit timeline */
  .audit-controls {
    display: flex; gap: 8px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    align-items: center;
    flex-wrap: wrap;
  }
  .audit-controls input,
  .audit-controls select {
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-family: inherit;
    outline: none;
  }
  .audit-controls input { flex: 1; min-width: 160px; }
  .audit-controls input:focus,
  .audit-controls select:focus { border-color: var(--accent); }
  .audit-controls .count {
    color: var(--muted); font-size: 11px; margin-left: auto;
    font-variant-numeric: tabular-nums;
  }

  .audit-list {
    max-height: 540px;
    overflow-y: auto;
  }
  .audit-row {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background-color 80ms;
  }
  .audit-row:hover { background: var(--surface-2); }
  .audit-row:last-child { border-bottom: none; }
  .audit-head {
    display: flex; gap: 10px;
    align-items: center;
  }
  .audit-status {
    width: 6px; align-self: stretch;
    border-radius: 3px;
    background: var(--green);
    flex-shrink: 0;
  }
  .audit-status.warn { background: var(--accent-2); }
  .audit-status.bad  { background: var(--red); }
  .audit-time {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    min-width: 60px;
    flex-shrink: 0;
  }
  .audit-agent {
    color: var(--accent);
    font-weight: 600;
    font-size: 12px;
  }
  .audit-event {
    color: var(--text);
    font-size: 12px;
  }
  .audit-event::before {
    content: "·"; margin: 0 6px; color: var(--muted);
  }
  .audit-dur {
    margin-left: auto;
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }
  .audit-dur .bar {
    width: 60px; height: 4px;
    background: var(--surface-3); border-radius: 2px;
    overflow: hidden;
  }
  .audit-dur .bar > span {
    display: block; height: 100%;
    background: var(--blue);
    transition: width 200ms;
  }
  .audit-dur .bar > span.warn { background: var(--accent-2); }
  .audit-dur .bar > span.bad  { background: var(--red); }
  .audit-payload {
    display: none;
    margin-top: 8px; margin-left: 16px;
    background: var(--surface-3);
    padding: 10px 12px;
    border-radius: 6px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 11px;
    color: var(--text-2);
    overflow-x: auto;
    white-space: pre;
    border: 1px solid var(--border);
  }
  .audit-row.open .audit-payload { display: block; }
  .audit-row .chev {
    color: var(--muted);
    font-size: 10px;
    margin-right: 4px;
    transition: transform 120ms;
  }
  .audit-row.open .chev { transform: rotate(90deg); }

  /* Memory tiers */
  .memory-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .memory-tier {
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 12px 10px;
    border-radius: 8px;
    text-align: center;
  }
  .memory-tier .count {
    font-size: 24px; font-weight: 600;
    color: var(--accent);
    font-variant-numeric: tabular-nums;
  }
  .memory-tier .label {
    font-size: 10px; color: var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 2px;
    font-weight: 500;
  }
  .memory-block {
    margin-top: 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    padding: 10px 12px;
    border-radius: 8px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 11px;
    color: var(--text-2);
    white-space: pre-wrap;
    max-height: 140px;
    overflow-y: auto;
  }

  /* Compliance */
  .compliance-list {
    display: flex; flex-direction: column; gap: 6px;
  }
  .compliance-tag {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 10px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-left: 3px solid var(--green);
    border-radius: 6px;
    font-size: 12px;
  }
  .compliance-tag .name { font-weight: 600; }
  .compliance-tag .section {
    color: var(--text-2);
    font-size: 11px;
  }
  .compliance-tag .notes {
    margin-left: auto;
    color: var(--muted);
    font-size: 10px;
    font-style: italic;
  }

  .empty {
    color: var(--muted);
    font-style: italic;
    padding: 16px;
    text-align: center;
    font-size: 12px;
  }

  footer {
    padding: 14px 24px;
    color: var(--muted);
    font-size: 11px;
    text-align: center;
    border-top: 1px solid var(--border);
  }
  footer a { color: var(--text-2); text-decoration: none; }
  footer a:hover { color: var(--text); }

  /* Scrollbars (subtle) */
  *::-webkit-scrollbar { width: 8px; height: 8px; }
  *::-webkit-scrollbar-thumb {
    background: var(--surface-3); border-radius: 4px;
  }
  *::-webkit-scrollbar-track { background: transparent; }

  /* Responsive: stack on narrow */
  @media (max-width: 900px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    main { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">
    <h1>{{TITLE}}</h1>
    <span class="pill"><span class="dot"></span>LARGESTACK Studio</span>
    <span class="meta" id="subtitle"></span>
  </div>
  <div>
    <span class="meta" id="generated"></span>
    <button id="theme-toggle" title="Toggle light/dark">☀ / ☾</button>
    <button id="copy-json" title="Copy raw JSON to clipboard">⧉ Copy JSON</button>
  </div>
</div>

<div class="kpi-row" id="kpis"></div>

<main>
  <div class="col-stack">
    <section id="graph">
      <header>
        <h2>Agent Graph</h2>
        <div class="actions">
          <button onclick="window.print()">⎙ Print</button>
        </div>
      </header>
      <div class="legend">
        <span class="item"><span class="swatch" style="border-color: var(--green)"></span>Start</span>
        <span class="item"><span class="swatch" style="border-color: var(--blue)"></span>Agent</span>
        <span class="item"><span class="swatch" style="border-color: var(--accent-2)"></span>Tool</span>
        <span class="item"><span class="swatch" style="border-color: var(--purple); border-style: dashed"></span>Decision</span>
        <span class="item"><span class="swatch" style="border-color: var(--red)"></span>End</span>
      </div>
      <div class="body">
        <svg id="graph-svg" role="img" aria-label="Agent execution graph"></svg>
      </div>
    </section>

    <section id="audit">
      <header>
        <h2>Audit Timeline</h2>
        <div class="actions">
          <button id="expand-all">⇕ Expand all</button>
          <button id="collapse-all">⇲ Collapse all</button>
        </div>
      </header>
      <div class="audit-controls">
        <input type="text" id="audit-filter" placeholder="Filter by agent or event…">
        <select id="audit-status-filter">
          <option value="">All status</option>
          <option value="ok">OK only</option>
          <option value="warn">Warn only</option>
          <option value="bad">Errors only</option>
        </select>
        <span class="count" id="audit-count"></span>
      </div>
      <div class="audit-list" id="audit-list"></div>
    </section>
  </div>

  <div class="col-stack">
    <section>
      <header><h2>Memory State</h2></header>
      <div class="body" id="memory"></div>
    </section>
    <section>
      <header><h2>India Compliance</h2></header>
      <div class="body" id="compliance"></div>
    </section>
  </div>
</main>

<footer>
  Generated by <a href="#" id="footer-brand">LARGESTACK Studio</a> ·
  RivaiLabs · DPDP / RBI / PMLA-compliant agent observability
</footer>

<script id="payload" type="application/json">
{{PAYLOAD_JSON}}
</script>
<script>
(function(){
  const data = JSON.parse(document.getElementById('payload').textContent);
  document.getElementById('subtitle').textContent = data.description || '';
  if (data.generated_at) {
    const d = new Date(data.generated_at * 1000);
    document.getElementById('generated').textContent =
      'Generated ' + d.toLocaleString();
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  // --- KPIs ---
  function severityFor(payload) {
    if (!payload || typeof payload !== 'object') return 'ok';
    if (payload.error || payload.failed === true) return 'bad';
    if (payload.warning || payload.verified === false) return 'warn';
    return 'ok';
  }

  function fmtMs(ms) {
    if (ms == null) return '—';
    if (ms < 1) return '<1ms';
    if (ms < 1000) return ms.toFixed(0) + 'ms';
    return (ms/1000).toFixed(2) + 's';
  }

  function renderKpis() {
    const events = data.audit || [];
    const total = events.length;
    const totalDur = events.reduce(
      (s,e) => s + (e.duration_ms||0), 0);
    const sorted = events.map(e => e.duration_ms||0).sort((a,b)=>a-b);
    const p50 = sorted.length ? sorted[Math.floor(sorted.length*0.5)] : 0;
    const errors = events.filter(e => severityFor(e.payload)==='bad').length;
    const status = errors > 0 ? 'bad' : (events.length ? 'ok' : 'warn');
    const statusLabel = errors > 0 ?
      errors + ' error' + (errors!==1?'s':'') :
      (events.length ? 'OK' : 'No runs');

    const cmpCount = (data.compliance || []).length;
    const memCount = data.memory ?
      (data.memory.core_count + data.memory.recall_count + data.memory.archival_count) : 0;

    document.getElementById('kpis').innerHTML = [
      kpiCard(status, 'Status', statusLabel,
        errors ? 'detected' : 'all events succeeded'),
      kpiCard('ok', 'Events', total, total ? 'audit entries logged' : '—'),
      kpiCard('ok', 'Total Duration', fmtMs(totalDur), 'wall clock'),
      kpiCard('ok', 'P50 Step', fmtMs(p50), 'median per event'),
      kpiCard('ok', 'Memory · Compliance',
        memCount + ' / ' + cmpCount,
        'entries · markers'),
    ].join('');
  }

  function kpiCard(severity, label, value, sub) {
    return (
      '<div class="kpi ' + severity + '">' +
      '<div class="label">' + escapeHtml(label) + '</div>' +
      '<div class="value">' + escapeHtml(value) + '</div>' +
      '<div class="sub">' + escapeHtml(sub) + '</div>' +
      '</div>'
    );
  }

  // --- Graph ---
  function renderGraph() {
    const svg = document.getElementById('graph-svg');
    const W = svg.clientWidth || 1200;
    const H_MIN = 720;
    const NODE_W = 180, NODE_H = 60;
    const PAD_X = 40, PAD_Y = 40;
    const COL_GAP = 90, ROW_GAP = 24;

    if (!data.nodes || !data.nodes.length) {
      svg.innerHTML =
        '<text x="50%" y="50%" text-anchor="middle" fill="#9aa7c0">' +
        'No nodes defined.</text>';
      return;
    }

    const inDeg = {}, outAdj = {};
    data.nodes.forEach(n => { inDeg[n.id] = 0; outAdj[n.id] = []; });
    data.edges.forEach(e => {
      inDeg[e.target] = (inDeg[e.target]||0)+1;
      outAdj[e.source].push(e.target);
    });
    const layers = [];
    const seen = new Set();
    let queue = data.nodes.filter(n => inDeg[n.id]===0).map(n => n.id);
    let layer = queue.slice();
    while (layer.length) {
      const next = [];
      for (const id of layer) {
        if (seen.has(id)) continue;
        seen.add(id);
        for (const t of outAdj[id]||[]) {
          if (!seen.has(t)) next.push(t);
        }
      }
      layers.push(layer);
      layer = next.filter(id => !seen.has(id));
    }
    const remaining = data.nodes.filter(n => !seen.has(n.id)).map(n=>n.id);
    if (remaining.length) layers.push(remaining);

    const positions = {};
    let maxRowCount = 0;
    layers.forEach((row, ci) => {
      const cx = PAD_X + ci * (NODE_W + COL_GAP);
      const totalH = row.length * (NODE_H + ROW_GAP) - ROW_GAP;
      maxRowCount = Math.max(maxRowCount, row.length);
      // We'll vertically center each column inside the viewBox after we
      // compute the final viewBox height below.
      row.forEach((id, ri) => {
        positions[id] = { x: cx, _ri: ri, _col: ci, _rowH: totalH };
      });
    });

    const totalCols = layers.length;
    const requiredW = PAD_X * 2 + totalCols * NODE_W +
                       Math.max(0, totalCols - 1) * COL_GAP;
    // Vertical sizing: enough room for the tallest column plus padding,
    // but never less than H_MIN so short flows don't look cramped.
    const requiredH = Math.max(
      H_MIN,
      PAD_Y * 2 + maxRowCount * (NODE_H + ROW_GAP) - ROW_GAP,
    );
    // Now finalize Y positions: center each column inside requiredH.
    Object.values(positions).forEach(p => {
      const startY = (requiredH - p._rowH) / 2;
      p.y = startY + p._ri * (NODE_H + ROW_GAP);
    });
    svg.setAttribute('viewBox',
      '0 0 ' + Math.max(W, requiredW) + ' ' + requiredH);

    const lines = data.edges.map(e => {
      const s = positions[e.source];
      const t = positions[e.target];
      if (!s || !t) return '';
      const x1 = s.x + NODE_W;
      const y1 = s.y + NODE_H/2;
      const x2 = t.x;
      const y2 = t.y + NODE_H/2;
      return (
        '<path class="edge-line" d="M ' + x1 + ' ' + y1 +
        ' C ' + (x1+45) + ' ' + y1 + ', ' + (x2-45) + ' ' + y2 +
        ', ' + x2 + ' ' + y2 + '" marker-end="url(#arrow)" />' +
        (e.label ?
          '<text class="edge-label" x="' + ((x1+x2)/2) +
          '" y="' + ((y1+y2)/2 - 6) + '" text-anchor="middle">' +
          escapeHtml(e.label) + '</text>'
          : '')
      );
    }).join('');

    function truncLabel(s, max) {
      s = String(s);
      if (s.length <= max) return s;
      return s.slice(0, max-1) + '…';
    }

    const nodes = data.nodes.map(n => {
      const p = positions[n.id];
      if (!p) return '';
      const cls = 'node-rect ' + (n.kind || 'agent');
      const kindLabel = (n.kind || 'agent').toUpperCase();
      return (
        '<g>' +
        '<rect class="' + cls + '" x="' + p.x + '" y="' + p.y +
        '" width="' + NODE_W + '" height="' + NODE_H + '" rx="8"/>' +
        '<text class="node-text" x="' + (p.x + NODE_W/2) +
        '" y="' + (p.y + NODE_H/2 - 2) + '" text-anchor="middle">' +
        escapeHtml(truncLabel(n.label, 24)) + '</text>' +
        '<text class="node-kind" x="' + (p.x + NODE_W/2) +
        '" y="' + (p.y + NODE_H - 12) + '" text-anchor="middle">' +
        escapeHtml(kindLabel) + '</text>' +
        '</g>'
      );
    }).join('');

    svg.innerHTML = (
      '<defs><marker id="arrow" markerWidth="10" markerHeight="10" ' +
      'refX="9" refY="3" orient="auto" markerUnits="strokeWidth">' +
      '<path class="edge-arrow" d="M0,0 L0,6 L9,3 z"/>' +
      '</marker></defs>' +
      lines + nodes
    );
  }

  // --- Audit ---
  let auditState = { filter: '', statusFilter: '' };

  function renderAudit() {
    const root = document.getElementById('audit-list');
    const events = (data.audit||[]).slice().sort(
      (a,b) => a.timestamp - b.timestamp);

    const maxDur = Math.max(1, ...events.map(e => e.duration_ms||0));
    const filtered = events.filter(e => {
      if (auditState.filter) {
        const f = auditState.filter.toLowerCase();
        if (!(e.agent||'').toLowerCase().includes(f) &&
            !(e.event||'').toLowerCase().includes(f)) return false;
      }
      if (auditState.statusFilter) {
        if (severityFor(e.payload) !== auditState.statusFilter) return false;
      }
      return true;
    });

    document.getElementById('audit-count').textContent =
      filtered.length + ' of ' + events.length + ' events';

    if (!events.length) {
      root.innerHTML = '<div class="empty">No audit events recorded.</div>';
      return;
    }
    if (!filtered.length) {
      root.innerHTML = '<div class="empty">No events match filter.</div>';
      return;
    }

    root.innerHTML = filtered.map((e, i) => {
      const sev = severityFor(e.payload);
      const t = new Date(e.timestamp * 1000).toLocaleTimeString(
        undefined, { hour12: false });
      const dur = e.duration_ms || 0;
      const durPct = Math.min(100, (dur/maxDur) * 100);
      const durSev = dur > 1000 ? 'warn' : (dur > 5000 ? 'bad' : '');
      const payloadJson = e.payload ?
        JSON.stringify(e.payload, null, 2) : '';
      const hasPayload = e.payload && Object.keys(e.payload).length > 0;
      return (
        '<div class="audit-row" data-idx="' + i + '">' +
          '<div class="audit-head">' +
            '<div class="audit-status ' + sev + '"></div>' +
            '<span class="chev">▶</span>' +
            '<span class="audit-time">' + t + '</span>' +
            '<span class="audit-agent">' + escapeHtml(e.agent) + '</span>' +
            '<span class="audit-event">' + escapeHtml(e.event) + '</span>' +
            '<span class="audit-dur">' +
              fmtMs(dur) +
              '<span class="bar"><span class="' + durSev +
              '" style="width:' + durPct + '%"></span></span>' +
            '</span>' +
          '</div>' +
          (hasPayload ?
            '<div class="audit-payload">' +
            escapeHtml(payloadJson) + '</div>' : '') +
        '</div>'
      );
    }).join('');

    // Click to expand
    root.querySelectorAll('.audit-row').forEach(row => {
      row.addEventListener('click', () => row.classList.toggle('open'));
    });
  }

  // --- Memory ---
  function renderMemory() {
    const root = document.getElementById('memory');
    if (!data.memory) {
      root.innerHTML = '<div class="empty">No memory state.</div>';
      return;
    }
    const m = data.memory;
    root.innerHTML = (
      '<div class="memory-grid">' +
      '<div class="memory-tier"><div class="count">' + m.core_count +
      '</div><div class="label">Core</div></div>' +
      '<div class="memory-tier"><div class="count">' + m.recall_count +
      '</div><div class="label">Recall</div></div>' +
      '<div class="memory-tier"><div class="count">' + m.archival_count +
      '</div><div class="label">Archival</div></div>' +
      '</div>' +
      '<div class="memory-block">' +
      escapeHtml(m.core_block_preview || '(empty)') +
      '</div>'
    );
  }

  // --- Compliance ---
  function renderCompliance() {
    const root = document.getElementById('compliance');
    if (!data.compliance || !data.compliance.length) {
      root.innerHTML = '<div class="empty">No compliance markers.</div>';
      return;
    }
    root.innerHTML = '<div class="compliance-list">' +
      data.compliance.map(c =>
        '<div class="compliance-tag" title="' +
        escapeHtml(c.notes||'') + '">' +
        '<span class="name">' + escapeHtml(c.name) + '</span>' +
        (c.section ? '<span class="section">' +
          escapeHtml(c.section) + '</span>' : '') +
        (c.notes ? '<span class="notes">' +
          escapeHtml(c.notes) + '</span>' : '') +
        '</div>'
      ).join('') +
    '</div>';
  }

  // --- Theme toggle ---
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
    renderGraph(); // re-paint to pick up new colors
  });

  // --- Copy JSON ---
  document.getElementById('copy-json').addEventListener('click', () => {
    const text = document.getElementById('payload').textContent.trim();
    navigator.clipboard.writeText(text).then(
      () => {
        const btn = document.getElementById('copy-json');
        const orig = btn.textContent;
        btn.textContent = '✓ Copied';
        setTimeout(() => btn.textContent = orig, 1200);
      },
      () => alert('Copy failed.'),
    );
  });

  // --- Audit filters ---
  document.getElementById('audit-filter').addEventListener('input', (e) => {
    auditState.filter = e.target.value;
    renderAudit();
  });
  document.getElementById('audit-status-filter').addEventListener(
    'change', (e) => {
    auditState.statusFilter = e.target.value;
    renderAudit();
  });
  document.getElementById('expand-all').addEventListener('click', () => {
    document.querySelectorAll('.audit-row').forEach(r => r.classList.add('open'));
  });
  document.getElementById('collapse-all').addEventListener('click', () => {
    document.querySelectorAll('.audit-row').forEach(r => r.classList.remove('open'));
  });

  renderKpis();
  renderGraph();
  renderAudit();
  renderMemory();
  renderCompliance();
})();
</script>
</body>
</html>
"""
