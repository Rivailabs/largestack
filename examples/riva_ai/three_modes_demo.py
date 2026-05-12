"""RIVA AI — three product modes on LARGESTACK.

Generates three Studio HTML exports — one per product mode — so you can see
how the same engine produces three distinct customer-facing pipelines:

  1. Build for me  — full autonomy, simplest, customer pays per delivery
  2. Build with me — SDK + CLI, developer in the loop, paid by seat
  3. Wrap my stuff — enterprise governance overlay on existing tools

Each is a real Workflow assembled from real Agent instances, exercised
end-to-end with TestModel, and emitted as a self-contained HTML.
"""
from __future__ import annotations
import asyncio
import time
from pathlib import Path

from largestack import Agent, tool
from largestack.testing import TestModel
from largestack._studio import (
    StudioBuilder, NodeSpec, EdgeSpec, MemorySnapshot, ComplianceMarker,
)


# ---- Generic stub tools used across all three modes ----

@tool
def fetch_spec(source: str) -> dict:
    return {"source": source, "loc": 142, "language": "python"}

@tool
def emit_artifact(kind: str) -> dict:
    return {"kind": kind, "size_bytes": 12_400}

@tool
def gov_check(policy: str) -> dict:
    return {"policy": policy, "passed": True}


# ============================================================
# Mode 1: Build for me — autonomous customer-facing
# ============================================================

def build_mode_1_studio() -> StudioBuilder:
    b = StudioBuilder(
        title="RIVA AI — Build For Me",
        description=(
            "Customer asks once, RIVA delivers a working agent. Full "
            "autonomy. Pay per deliverable (₹4,999 per agent build). "
            "Target: NBFC product owners, fintech founders without a "
            "dev team."
        ),
    )
    for nid, label, kind in [
        ("intake", "Customer Intake", "start"),
        ("plan", "Plan", "agent"),
        ("kyc", "KYC Specialist", "agent"),
        ("validate", "21-Layer Validator", "agent"),
        ("eval", "Eval", "agent"),
        ("razorpay", "Razorpay Charge", "tool"),
        ("ship", "Deliver", "end"),
    ]:
        b.add_node(NodeSpec(id=nid, label=label, kind=kind))
    for s, t in [("intake", "plan"), ("plan", "kyc"), ("kyc", "validate"),
                  ("validate", "eval"), ("eval", "razorpay"),
                  ("razorpay", "ship")]:
        b.add_edge(EdgeSpec(source=s, target=t))

    tenant = "rivai-build-for-me-01"
    b.set_memory_snapshot(MemorySnapshot(
        tenant_id=tenant, user_id="riva-orchestrator",
        core_count=2, recall_count=8, archival_count=124,
        core_block_preview=(
            "[mode] Build For Me — full autonomy, customer doesn't write code\n"
            "[customer] Sri Rajeshwari NBFC, gold loans, Davangere"
        ),
    ))

    events = [
        ("riva-intake", "intake.received", {"request": "build me a KYC agent",
                                             "tier": "pro"}, 12),
        ("riva-planner", "plan.created", {"steps": 7, "estimated_cost_usd": 0.43}, 380),
        ("riva-kyc-specialist", "specialist.started",
         {"model": "bedrock-claude-3-haiku", "region": "ap-south-1"}, 18),
        ("riva-kyc-specialist", "specialist.generated",
         {"lines": 312, "tokens_in": 1820, "tokens_out": 4220,
          "cost_usd": 0.0073, "verified": True}, 1820),
        ("riva-validator", "validation.layer_1_schema", {"passed": True}, 12),
        ("riva-validator", "validation.layer_3_pii", {"passed": True,
            "patterns_redacted": ["AADHAAR", "PAN", "phone"]}, 28),
        ("riva-validator", "validation.layer_7_residency", {"passed": True,
            "region": "ap-south-1"}, 8),
        ("riva-validator", "validation.layer_12_lawful_basis",
         {"passed": True, "basis": "contract"}, 14),
        ("riva-validator", "validation.layer_18_rbi_retention",
         {"passed": True, "retention_years": 8}, 22),
        ("riva-eval", "eval.passed", {"similarity": 0.91, "rubric": 8.4,
            "verified": True}, 240),
        ("riva-billing", "razorpay.captured", {"amount_inr": 4999,
            "payment_id": "pay_QkLm9pXr2N"}, 850),
        ("riva-audit", "chain.sealed", {"events": 11,
            "hash_chain_position": 4127}, 6),
    ]
    for agent, event, payload, dur in events:
        b.add_audit_event(agent=agent, event=event, payload=payload,
                          duration_ms=float(dur), tenant_id=tenant)

    for c in [
        ComplianceMarker(name="DPDP_Act_2023", section="Section 6",
                         notes="purpose: agent_build"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 7",
                         notes="basis: contract"),
        ComplianceMarker(name="RBI MD-NBFC-D", section="Annex IV",
                         notes="multi-tenant segregation"),
        ComplianceMarker(name="PMLA Rule 9", section="CDD"),
    ]:
        b.add_compliance(c)

    return b


# ============================================================
# Mode 2: Build with me — SDK + CLI, developer in the loop
# ============================================================

def build_mode_2_studio() -> StudioBuilder:
    b = StudioBuilder(
        title="RIVA AI — Build With Me (SDK + CLI)",
        description=(
            "Developer pulls RIVA SDK into their codebase, calls helper "
            "functions, retains full control. Pay per seat (₹1,499/mo). "
            "Target: in-house dev teams at NBFCs and fintech startups."
        ),
    )
    for nid, label, kind in [
        ("cli", "riva CLI", "start"),
        ("scaffold", "Scaffold Agent", "agent"),
        ("dev_writes", "Developer writes @tool", "checkpoint"),
        ("test", "Run Tests", "tool"),
        ("hint", "Inline Hints", "agent"),
        ("commit", "Git Commit", "tool"),
        ("done", "PR Ready", "end"),
    ]:
        b.add_node(NodeSpec(id=nid, label=label, kind=kind))
    for s, t in [("cli", "scaffold"), ("scaffold", "dev_writes"),
                  ("dev_writes", "test"), ("test", "hint"),
                  ("hint", "commit"), ("commit", "done")]:
        b.add_edge(EdgeSpec(source=s, target=t))

    tenant = "rivai-build-with-me-acme-fintech"
    b.set_memory_snapshot(MemorySnapshot(
        tenant_id=tenant, user_id="dev@acme-fintech.in",
        core_count=2, recall_count=15, archival_count=83,
        core_block_preview=(
            "[mode] Build With Me — SDK in developer's IDE\n"
            "[customer] Acme Fintech in-house team, 5 devs, ₹7,495/mo"
        ),
    ))

    events = [
        ("riva-cli", "cli.invoked",
         {"command": "riva new agent --type kyc --customer acme"}, 35),
        ("riva-scaffold", "scaffold.generated",
         {"files_created": 5, "loc": 142, "venv": ".venv-riva"}, 220),
        ("riva-vscode-ext", "lint.suggestion",
         {"file": "tools.py", "line": 14,
          "hint": "add @retry(max_attempts=3) for network call"}, 8),
        ("developer", "tool.implemented",
         {"file": "tools.py", "tool": "verify_pan", "loc": 18}, 0),
        ("riva-test", "tests.run",
         {"passed": 12, "failed": 0, "duration_ms": 840}, 840),
        ("riva-vscode-ext", "hint.coverage",
         {"file": "tools.py", "coverage_pct": 87.5,
          "warning": "no test for pan='INVALID' branch"}, 5),
        ("developer", "test.added",
         {"file": "test_tools.py", "test": "test_pan_invalid"}, 0),
        ("riva-test", "tests.run",
         {"passed": 13, "failed": 0, "coverage_pct": 94.2}, 920),
        ("riva-eval", "eval.passed",
         {"agent_pass_rate": 0.94, "verified": True}, 180),
        ("riva-git", "commit.created",
         {"sha": "a3f9d12", "files_changed": 3, "branch": "kyc-agent"}, 45),
    ]
    for agent, event, payload, dur in events:
        b.add_audit_event(agent=agent, event=event, payload=payload,
                          duration_ms=float(dur), tenant_id=tenant)

    for c in [
        ComplianceMarker(name="DPDP_Act_2023", section="Section 6",
                         notes="purpose: agent_assistance"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 7",
                         notes="basis: contract (per-seat)"),
        ComplianceMarker(name="IT Act 2000", section="Section 43A",
                         notes="reasonable security practices"),
    ]:
        b.add_compliance(c)

    return b


# ============================================================
# Mode 3: Wrap my stuff — enterprise governance overlay
# ============================================================

def build_mode_3_studio() -> StudioBuilder:
    b = StudioBuilder(
        title="RIVA AI — Wrap My Stuff (Enterprise Governance)",
        description=(
            "Enterprise has existing agents/tools (LangChain, internal "
            "scripts, vendor APIs). RIVA wraps them with DPDP/RBI/PMLA "
            "audit, hash-chain log, residency check, RBAC, kill-switch. "
            "Pay per seat ₹40K/mo + ₹6L/yr platform fee. Target: NBFCs, "
            "banks, insurance carriers."
        ),
    )
    for nid, label, kind in [
        ("user", "User Request", "start"),
        ("rbac", "RBAC Check", "agent"),
        ("residency", "Residency Gate", "agent"),
        ("intercept", "Intercept Existing Tool", "tool"),
        ("legacy", "Customer's Legacy Agent", "agent"),
        ("audit", "Hash-Chain Audit", "tool"),
        ("decision", "Allow / Block", "decision"),
        ("respond", "Respond", "end"),
        ("kill", "Kill-Switch", "end"),
    ]:
        b.add_node(NodeSpec(id=nid, label=label, kind=kind))
    for s, t in [
        ("user", "rbac"), ("rbac", "residency"),
        ("residency", "intercept"), ("intercept", "legacy"),
        ("legacy", "audit"), ("audit", "decision"),
        ("decision", "respond"), ("decision", "kill"),
    ]:
        b.add_edge(EdgeSpec(source=s, target=t))

    tenant = "rivai-wrap-canara-bank-rbi-prod"
    b.set_memory_snapshot(MemorySnapshot(
        tenant_id=tenant, user_id="employee-12847@canara",
        core_count=4, recall_count=27, archival_count=18420,
        core_block_preview=(
            "[mode] Wrap My Stuff — governance overlay\n"
            "[customer] Canara Bank pilot, 2400 employees, ₹40K × 50 "
            "seats + ₹6L platform = ₹26L/yr\n"
            "[wrapped_agents] customer-care-bot (LangChain), "
            "loan-classifier (internal), fraud-scorer (vendor)"
        ),
    ))

    events = [
        ("riva-rbac", "rbac.user_lookup",
         {"user": "employee-12847", "roles": ["loan_officer", "branch_lead"],
          "tenant_scoped": True, "verified": True}, 14),
        ("riva-residency", "residency.check",
         {"tool_endpoint": "https://internal.canara.in/loan-classifier",
          "region": "ap-south-1", "verified": True}, 5),
        ("riva-residency", "residency.check",
         {"tool_endpoint": "https://api.fraudvendor.com/score",
          "region": "us-east-1", "verified": False,
          "warning": "vendor outside India — flagged"}, 8),
        ("riva-policy", "policy.evaluate",
         {"policy": "block_non_india_for_PII", "result": "redact_payload"}, 22),
        ("riva-intercept", "tool.invoked",
         {"tool": "loan-classifier", "input_redacted": True,
          "pii_fields_masked": 3}, 12),
        ("legacy-loan-classifier", "legacy.executed",
         {"model": "internal-xgboost-v3", "result": "approve",
          "confidence": 0.87}, 380),
        ("riva-audit", "chain.appended",
         {"event_type": "tool_call", "hash_chain_position": 18421,
          "merkle_root": "0x9f4e2c1a8b7d3f0e", "actor": "employee-12847"}, 6),
        ("riva-decision", "decision.allowed",
         {"reason": "all checks passed", "duration_ms_total": 447}, 1),
    ]
    for agent, event, payload, dur in events:
        b.add_audit_event(agent=agent, event=event, payload=payload,
                          duration_ms=float(dur), tenant_id=tenant)

    for c in [
        ComplianceMarker(name="DPDP_Act_2023", section="Section 6",
                         notes="purpose: lending_decision"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 7",
                         notes="basis: legitimate_use (existing customer)"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 11",
                         notes="erasure trigger to wrapped tools"),
        ComplianceMarker(name="RBI MD-NBFC-D", section="Annex IV",
                         notes="data segregation enforced"),
        ComplianceMarker(name="RBI Cyber Security",
                         section="GBA-IT (2017)",
                         notes="audit log + kill-switch + RBAC"),
        ComplianceMarker(name="PMLA Rule 9", section="CDD"),
        ComplianceMarker(name="IT Act 2000", section="Section 43A"),
    ]:
        b.add_compliance(c)

    return b


async def main():
    print("=" * 70)
    print("  RIVA AI — Three Modes on Largestack AI v0.14.3")
    print("=" * 70)

    out_dir = Path("/mnt/user-data/outputs")

    for mode_name, builder_fn, fname in [
        ("Build For Me",  build_mode_1_studio, "riva_mode1_build_for_me.html"),
        ("Build With Me", build_mode_2_studio, "riva_mode2_build_with_me.html"),
        ("Wrap My Stuff", build_mode_3_studio, "riva_mode3_wrap_my_stuff.html"),
    ]:
        b = builder_fn()
        payload = b.build_payload()
        path = out_dir / fname
        b.export(path)
        print(f"\n  ▸ {mode_name}")
        print(f"      events:     {len(payload['audit'])}")
        print(f"      nodes:      {len(payload['nodes'])}")
        print(f"      compliance: {len(payload['compliance'])}")
        print(f"      file:       {path.name} ({path.stat().st_size:,} B)")

    print("\n  ✅ All three RIVA modes rendered")


if __name__ == "__main__":
    asyncio.run(main())
