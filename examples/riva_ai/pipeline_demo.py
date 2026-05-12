"""RIVA AI — production simulation on Largestack AI v0.14.3.

Models the actual RIVA AI v5.0 architecture from Sachith's portfolio:

  - 15 specialized agents
  - 8-in-1 architecture: SDK + CLI + MCP + VS Code + Studio + Cloud +
    Wrapper + Workflow
  - 21-layer validation pipeline
  - 7 LLM providers with FallbackRouter
  - Hybrid RAG (vector + BM25)
  - Razorpay + Stripe billing tools
  - Three product modes:
      Build for me  — full autonomy, customer-facing
      Build with me — SDK + CLI integration for developers
      Wrap my stuff — enterprise governance overlay on existing tools

Runs end-to-end on LARGESTACK, emits a single self-contained HTML showing the
pipeline graph, audit timeline, memory state, and India-compliance markers.
"""
from __future__ import annotations
import asyncio
import time
from pathlib import Path

from largestack import Agent, Workflow, tool, create_guardrails
from largestack.testing import TestModel
from largestack._studio import (
    StudioBuilder, NodeSpec, EdgeSpec, MemorySnapshot, ComplianceMarker,
)
from largestack._integrations.litellm_bridge import FallbackRouter, ProviderRoute


# ============================================================
# RIVA AI tools — 21-layer validation pipeline
# ============================================================

@tool
def riva_intake(request_text: str, mode: str = "build_for_me") -> dict:
    """Intake: classify customer request and pick product mode."""
    return {
        "request_id": "RIVA-2026-0421",
        "mode": mode,
        "customer_tier": "pro",
        "language_detected": "en",
        "intent": "build_kyc_agent_for_nbfc",
    }


@tool
def riva_router(intent: str) -> dict:
    """Routing: pick which RIVA agent (1 of 15) handles the request."""
    return {
        "selected_agent": "kyc_specialist",
        "confidence": 0.94,
        "alternatives": ["compliance_specialist", "fintech_generalist"],
    }


@tool
def riva_validate_layer(layer: int, payload: dict) -> dict:
    """One of 21 validation layers. Layers cover: schema, PII, injection,
    cost, residency, lawful basis, retention, RBAC, signature, idempotency,
    rate limit, hallucination, citation, toxicity, length, language, format,
    factuality, jailbreak, off-topic, brand-safety."""
    return {"layer": layer, "passed": True, "warnings": []}


@tool
def riva_hybrid_rag(query: str, top_k: int = 5) -> dict:
    """Hybrid retrieval: vector + BM25 + RRF fusion."""
    return {
        "query": query,
        "vector_hits": 8,
        "bm25_hits": 12,
        "fused_top_k": top_k,
        "sources": ["RBI_MD-NBFC-D.pdf", "DPDP_Act_2023.pdf",
                    "PMLA_Rule_9.pdf"],
    }


@tool
def riva_llm_call(prompt_tokens: int, model: str) -> dict:
    """LLM call routed via FallbackRouter (7 providers)."""
    return {
        "model": model,
        "input_tokens": prompt_tokens,
        "output_tokens": 420,
        "cost_usd": 0.0073,
        "provider": "bedrock-ap-south-1",
    }


@tool
def riva_assemble_output(parts: list, format: str) -> dict:
    """Assemble final output (code, doc, agent config, etc.)."""
    return {"format": format, "parts_count": len(parts), "size_bytes": 14_320}


@tool
def riva_razorpay_charge(amount_inr: int, customer_id: str) -> dict:
    """Razorpay billing integration."""
    return {
        "amount_inr": amount_inr,
        "customer_id": customer_id,
        "payment_id": "pay_QkLm9pXr2N",
        "status": "captured",
    }


@tool
def riva_audit_emit(event: str, scope: str) -> dict:
    """Hash-chain audit emission."""
    return {"event": event, "scope": scope, "hash_chain_position": 4127}


@tool
def riva_eval_score(reference: str, generated: str) -> dict:
    """Eval scoring: semantic similarity + custom rubric."""
    return {"similarity": 0.91, "rubric_score": 8.4, "passed": True}


# ============================================================
# RIVA AI agents — 15-agent crew
# ============================================================

def make_intake_agent():
    return Agent(
        name="riva-intake",
        instructions=(
            "Classify the customer's request, detect language, identify the "
            "appropriate RIVA product mode (Build for me / Build with me / "
            "Wrap my stuff), and emit an intake record."
        ),
        llm="openai/gpt-4o-mini",
        tools=[riva_intake],
        cost_budget=0.05,
        max_turns=3,
    )


def make_router_agent():
    return Agent(
        name="riva-router",
        instructions=(
            "Given an intake record, select the most appropriate specialist "
            "agent from the 15-agent RIVA crew. Tier the request by "
            "complexity and urgency."
        ),
        llm="openai/gpt-4o-mini",
        tools=[riva_router],
        cost_budget=0.05,
        max_turns=3,
    )


def make_kyc_specialist():
    # In production this uses the FallbackRouter for compliance-grade
    # India-residency LLM routing
    from largestack._integrations.litellm_bridge import LiteLLMProvider
    router = FallbackRouter([
        ProviderRoute(
            provider=LiteLLMProvider(
                model="bedrock/anthropic.claude-3-haiku-20240307-v1:0",
                region="ap-south-1",
            ),
            label="bedrock-mumbai",
        ),
        ProviderRoute(
            provider=LiteLLMProvider(
                model="azure/gpt-4o-mini", region="centralindia",
            ),
            label="azure-india-central",
        ),
    ])
    return Agent(
        name="riva-kyc-specialist",
        instructions=(
            "You are the RIVA KYC specialist. Build complete KYC agents for "
            "Indian NBFCs, ensuring DPDP Act 2023 (Section 6, 7, 8, 11), "
            "RBI MD-NBFC-D, and PMLA Rule 9 compliance. Always verify with "
            "Aadhaar OKYC, PAN, and CIBIL. Mask PII in all outputs. "
            "Generate the agent code and the agent.yaml."
        ),
        llm=router,
        tools=[riva_hybrid_rag, riva_llm_call, riva_validate_layer,
               riva_assemble_output],
        guardrails=create_guardrails(
            pii=True, injection=True, toxicity=True,
            pii_action="redact", injection_sensitivity="high",
        ),
        cost_budget=0.40,
        max_turns=12,
    )


def make_validator():
    return Agent(
        name="riva-validator",
        instructions=(
            "Run the 21-layer validation pipeline on the specialist's "
            "output. Reject if any critical layer fails."
        ),
        llm="openai/gpt-4o-mini",
        tools=[riva_validate_layer],
        cost_budget=0.10,
        max_turns=21,
    )


def make_eval_agent():
    return Agent(
        name="riva-eval",
        instructions=(
            "Score the generated output against the reference. Pass-fail "
            "threshold 0.85 similarity, 7.0 rubric."
        ),
        llm="openai/gpt-4o-mini",
        tools=[riva_eval_score],
        cost_budget=0.05,
        max_turns=3,
    )


def make_billing_agent():
    return Agent(
        name="riva-billing",
        instructions=(
            "Charge the customer for the completed work via Razorpay. "
            "Emit hash-chain audit event."
        ),
        llm="openai/gpt-4o-mini",
        tools=[riva_razorpay_charge, riva_audit_emit],
        cost_budget=0.02,
        max_turns=2,
    )


# ============================================================
# Pipeline runner — exercises the agents and records audit events
# ============================================================

async def run_riva_pipeline(builder: StudioBuilder, request_text: str):
    """Run the full RIVA pipeline and emit Studio audit events for each step."""

    intake = make_intake_agent()
    router = make_router_agent()
    kyc = make_kyc_specialist()
    validator = make_validator()
    evaler = make_eval_agent()
    billing = make_billing_agent()

    tenant = "rivai-customer-srn-nbfc-001"

    # Step 1: Intake
    t0 = time.time()
    with intake.override(model=TestModel(call_tools=["riva_intake"])):
        r = await intake.run(request_text)
    builder.add_audit_event(
        agent="riva-intake", event="intake.classified",
        payload={"mode": "build_for_me", "intent": "build_kyc_agent_for_nbfc",
                 "language": "en", "customer_tier": "pro",
                 "trace_id": r.trace_id[:8]},
        duration_ms=(time.time()-t0)*1000, tenant_id=tenant,
    )

    # Step 2: Router
    t0 = time.time()
    with router.override(model=TestModel(call_tools=["riva_router"])):
        r = await router.run("intent=build_kyc_agent_for_nbfc")
    builder.add_audit_event(
        agent="riva-router", event="router.selected",
        payload={"selected": "riva-kyc-specialist", "confidence": 0.94,
                 "alt_count": 2},
        duration_ms=(time.time()-t0)*1000, tenant_id=tenant,
    )

    # Step 3: Hybrid RAG retrieval
    t0 = time.time()
    builder.add_audit_event(
        agent="riva-rag", event="rag.hybrid_search",
        payload={"vector_hits": 8, "bm25_hits": 12, "fused_top_k": 5,
                 "sources": ["RBI_MD-NBFC-D.pdf", "DPDP_Act_2023.pdf",
                             "PMLA_Rule_9.pdf"]},
        duration_ms=145.0, tenant_id=tenant,
    )

    # Step 4: KYC specialist generates the agent
    t0 = time.time()
    with kyc.override(model=TestModel(
            call_tools=["riva_validate_layer", "riva_llm_call",
                        "riva_assemble_output"],
            custom_output_text=(
                "Generated NBFC KYC agent: 312 lines Python, "
                "agent.yaml with DPDP/RBI/PMLA markers."))):
        r = await kyc.run("Build me a KYC agent for Sri Rajeshwari NBFC")
    builder.add_audit_event(
        agent="riva-kyc-specialist", event="specialist.generated",
        payload={"output_format": "python+yaml", "lines": 312,
                 "tokens_in": 1820, "tokens_out": 4220,
                 "cost_usd": 0.0073, "provider": "bedrock-ap-south-1",
                 "verified": True},
        duration_ms=(time.time()-t0)*1000 + 1820,  # simulated LLM latency
        tenant_id=tenant,
    )

    # Step 5: 21-layer validation (we'll record 5 representative layers)
    layer_specs = [
        (1, "schema_check", 12.0, True),
        (3, "pii_redaction", 28.0, True),
        (7, "india_residency", 8.0, True),
        (12, "lawful_basis_check", 14.0, True),
        (18, "rbi_retention_check", 22.0, True),
    ]
    for layer_num, layer_name, dur, ok in layer_specs:
        builder.add_audit_event(
            agent="riva-validator", event=f"validation.layer_{layer_num}",
            payload={"layer": layer_num, "name": layer_name, "passed": ok,
                     "warnings": []},
            duration_ms=dur, tenant_id=tenant,
        )

    # One layer with a warning
    builder.add_audit_event(
        agent="riva-validator", event="validation.layer_15",
        payload={"layer": 15, "name": "language_consistency", "passed": True,
                 "warning": "mixed Hindi/English in 2 sections — acceptable"},
        duration_ms=18.0, tenant_id=tenant,
    )

    # Step 6: Eval
    t0 = time.time()
    with evaler.override(model=TestModel(call_tools=["riva_eval_score"])):
        r = await evaler.run("evaluate generated output")
    builder.add_audit_event(
        agent="riva-eval", event="eval.scored",
        payload={"similarity": 0.91, "rubric_score": 8.4, "passed": True,
                 "threshold_similarity": 0.85, "threshold_rubric": 7.0},
        duration_ms=(time.time()-t0)*1000, tenant_id=tenant,
    )

    # Step 7: Billing (Razorpay)
    t0 = time.time()
    with billing.override(model=TestModel(
            call_tools=["riva_razorpay_charge", "riva_audit_emit"])):
        r = await billing.run("charge customer for completed agent build")
    builder.add_audit_event(
        agent="riva-billing", event="billing.captured",
        payload={"amount_inr": 4999, "customer_id": tenant,
                 "payment_id": "pay_QkLm9pXr2N", "status": "captured",
                 "razorpay_settlement": "T+2"},
        duration_ms=(time.time()-t0)*1000 + 850,  # Razorpay API latency
        tenant_id=tenant,
    )

    # Step 8: Final hash-chain audit emit
    builder.add_audit_event(
        agent="riva-audit", event="audit.chain_sealed",
        payload={"hash_chain_position": 4127,
                 "merkle_root": "0x9f4e2c1a8b7d3f0e",
                 "events_in_run": 14, "tenant": tenant},
        duration_ms=6.0, tenant_id=tenant,
    )


# ============================================================
# Build the visualisation
# ============================================================

def build_studio() -> StudioBuilder:
    b = StudioBuilder(
        title="RIVA AI v5.0 — Build For Me · Production Pipeline",
        description=(
            "Customer asked: 'Build me a KYC agent for Sri Rajeshwari NBFC.' "
            "RIVA orchestrated 6 specialist agents through a 21-layer "
            "validation pipeline, hybrid RAG, India-residency LLM routing, "
            "and Razorpay billing — end-to-end."
        ),
    )

    # ---- Graph nodes ----
    nodes = [
        ("intake",      "Intake",                "start"),
        ("router",      "Router",                "agent"),
        ("rag",         "Hybrid RAG",            "tool"),
        ("kyc",         "KYC Specialist",        "agent"),
        ("validator",   "21-Layer Validator",    "agent"),
        ("eval",        "Eval Agent",            "agent"),
        ("decision",    "Pass / Fail",           "decision"),
        ("billing",     "Razorpay Billing",      "tool"),
        ("audit",       "Hash-Chain Audit",      "tool"),
        ("ship",        "Deliver Agent",         "end"),
    ]
    for nid, label, kind in nodes:
        b.add_node(NodeSpec(id=nid, label=label, kind=kind))

    edges = [
        ("intake", "router"),
        ("router", "rag"),
        ("router", "kyc"),
        ("rag", "kyc"),
        ("kyc", "validator"),
        ("validator", "eval"),
        ("eval", "decision"),
        ("decision", "billing"),
        ("decision", "audit"),
        ("billing", "ship"),
        ("audit", "ship"),
    ]
    for s, t in edges:
        b.add_edge(EdgeSpec(source=s, target=t))

    # ---- Memory state (Letta 3-tier, RIVA's persona + customer prefs) ----
    b.set_memory_snapshot(MemorySnapshot(
        tenant_id="rivai-customer-srn-nbfc-001",
        user_id="riva-orchestrator",
        core_count=3,
        recall_count=18,
        archival_count=247,
        core_block_preview=(
            "[persona] You are RIVA AI — Real Intelligence, Volitional "
            "Agents. Tagline: Not just intelligent. Intentional.\n"
            "[customer] Sri Rajeshwari NBFC, gold-loan fintech, Davangere KA.\n"
            "[constraints] India residency, DPDP §6/§7/§11, RBI MD-NBFC-D, "
            "PMLA Rule 9, 8-year retention."
        ),
    ))

    # ---- Compliance markers ----
    for marker in [
        ComplianceMarker(name="DPDP_Act_2023", section="Section 6",
                         notes="purpose: agent_build_for_nbfc_customer"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 7",
                         notes="lawful basis: contract"),
        ComplianceMarker(name="DPDP_Act_2023", section="Section 11",
                         notes="erasure capable via /forget endpoint"),
        ComplianceMarker(name="RBI MD-NBFC-D", section="Annex IV",
                         notes="multi-tenant data segregation"),
        ComplianceMarker(name="PMLA Rule 9", section="CDD",
                         notes="customer due diligence captured in audit"),
        ComplianceMarker(name="IT Act 2000", section="Section 43A",
                         notes="reasonable security practices"),
    ]:
        b.add_compliance(marker)

    return b


async def main():
    print("=" * 70)
    print("  RIVA AI Pipeline — running on Largestack AI v0.14.3")
    print("=" * 70)

    b = build_studio()

    print("\n  ▸ Running 6 agents through 21-layer validation pipeline...")
    t0 = time.time()
    await run_riva_pipeline(
        b, "Build me a KYC agent for Sri Rajeshwari NBFC")
    elapsed = time.time() - t0
    print(f"  ▸ Pipeline completed in {elapsed:.2f}s")

    payload = b.build_payload()
    print(f"\n  Audit events recorded: {len(payload['audit'])}")
    print(f"  Graph nodes:           {len(payload['nodes'])}")
    print(f"  Graph edges:           {len(payload['edges'])}")
    print(f"  Compliance markers:    {len(payload['compliance'])}")

    out = Path("/mnt/user-data/outputs/riva_ai_pipeline.html")
    b.export(out)
    print(f"\n  ▸ Wrote: {out}")
    print(f"    Size:  {out.stat().st_size:,} bytes")
    print("\n  ✅ RIVA AI pipeline visualisation ready")


if __name__ == "__main__":
    asyncio.run(main())
