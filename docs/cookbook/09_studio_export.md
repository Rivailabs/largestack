# Recipe 09 — Studio Export Walkthrough

**Use case:** Generate a single-HTML visualizer of your agent — graph
topology + audit trail + memory state + compliance markers — to share
with non-technical stakeholders, auditors, or customers.

## What you get

A self-contained HTML file (no server, no build, no dependencies) that
renders:

- **Agent graph** — nodes (start/agent/tool/decision/end) connected by edges
- **Audit timeline** — every event with timestamp + payload
- **Memory state** — counts of core/recall/archival entries + core block preview
- **Compliance markers** — DPDP/RBI tags from agent.yaml

## CLI usage

```bash
# Basic
largestack studio-export --agent agent.yaml -o studio.html

# With audit log
largestack studio-export \
  --agent agent.yaml \
  -o studio.html \
  --audit-log audit_export.json
```

## Programmatic usage

```python
import asyncio
import time
from largestack._studio import (
    StudioBuilder, NodeSpec, EdgeSpec,
    ComplianceMarker, MemorySnapshot,
    from_memory_manager, from_audit_log_records,
)
from largestack._memory.long_term import LongTermMemoryManager

async def export_studio_for_kyc_agent(tenant_id: str, user_id: str):
    builder = StudioBuilder(
        title="KYC Agent",
        description="DPDP-compliant KYC pipeline",
    )

    # Graph
    builder.add_node(NodeSpec(id="start", label="Start", kind="start"))
    builder.add_node(NodeSpec(
        id="consent", label="Consent Check", kind="decision",
    ))
    builder.add_node(NodeSpec(
        id="aadhaar", label="Aadhaar OKYC", kind="tool",
    ))
    builder.add_node(NodeSpec(
        id="pan", label="PAN Verify", kind="tool",
    ))
    builder.add_node(NodeSpec(
        id="match", label="Cross-Match", kind="agent",
    ))
    builder.add_node(NodeSpec(id="end", label="End", kind="end"))

    builder.add_edge(EdgeSpec(source="start", target="consent"))
    builder.add_edge(EdgeSpec(
        source="consent", target="aadhaar", label="consent_ok",
    ))
    builder.add_edge(EdgeSpec(
        source="consent", target="end", label="no_consent",
    ))
    builder.add_edge(EdgeSpec(source="aadhaar", target="pan"))
    builder.add_edge(EdgeSpec(source="pan", target="match"))
    builder.add_edge(EdgeSpec(source="match", target="end"))

    # Memory snapshot — pulled live from the manager
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id=user_id,
    )
    builder.set_memory_snapshot(await from_memory_manager(memory))

    # Audit events from a LARGESTACK audit log export
    builder.add_audit_event(
        timestamp=time.time() - 120,
        agent="consent_check",
        event="consent_verified",
        payload={"token": "dpdp_consent_abc123"},
        duration_ms=42.0,
    )
    builder.add_audit_event(
        timestamp=time.time() - 90,
        agent="aadhaar_okyc",
        event="otp_sent",
        payload={"masked": "XXXX-XXXX-9012"},
    )
    builder.add_audit_event(
        timestamp=time.time() - 60,
        agent="aadhaar_okyc",
        event="okyc_verified",
        duration_ms=2340.0,
    )

    # Compliance markers
    for marker in [
        ("DPDP_Act_2023", "Section 6", "consent-bound PII"),
        ("RBI_MD_KYC", "Section 11", "video-KYC fallback"),
        ("PMLA_2002", "Rule 9", "CDD complete"),
    ]:
        builder.add_compliance(ComplianceMarker(
            name=marker[0], section=marker[1], notes=marker[2],
        ))

    # Export
    builder.export("/tmp/kyc_studio.html")


asyncio.run(export_studio_for_kyc_agent("nbfc1", "user42"))
```

## Auto-generating from a live run

To capture an actual LARGESTACK run as a Studio HTML:

```python
from largestack._compliance import AuditLogger

async def capture_and_export(tenant_id: str, user_id: str):
    # Get the most recent audit events
    audit = AuditLogger(tenant_id=tenant_id)
    records = await audit.query(
        filters={"user_id": user_id},
        limit=100,
    )

    # Convert to studio events
    events = from_audit_log_records([
        r.to_dict() for r in records
    ])

    builder = StudioBuilder(title=f"Run for {user_id}")
    # ... build graph ...
    for ev in events:
        builder.add_audit_event(
            timestamp=ev.timestamp,
            agent=ev.agent, event=ev.event,
            payload=ev.payload,
            duration_ms=ev.duration_ms,
        )
    builder.export(f"/exports/run_{user_id}.html")
```

## What it looks like

The exported HTML uses:

- Dark theme (slate-900 background, sky-400 accents)
- SVG layered BFS layout (no external graph library)
- Inline CSS + JS — no external assets
- ~30 KB per export — emailable, shareable, archivable

## Why this matters

- **Auditors**: open the HTML in a browser, see compliance posture in 30 seconds
- **Non-technical stakeholders**: visualise what the agent does without reading code
- **Reproducibility**: HTML is timestamped + checksummable; serves as evidence

## Limitations vs LangGraph Studio

| Feature | LARGESTACK Studio v0 | LangGraph Studio |
|---|---|---|
| Single-file HTML | ✅ | ❌ (desktop app) |
| Time-travel state editing | ❌ (use checkpoints) | ✅ |
| Hot reload | ❌ (re-export) | ✅ |
| Free / no account | ✅ | ❌ (LangSmith required) |
| Indian compliance display | ✅ | ❌ |

For richer interactive features, plan to upgrade to LARGESTACK Studio v1
(roadmap: server-mode + WebSocket replay).
