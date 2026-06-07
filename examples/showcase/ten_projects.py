"""Largestack AI — 10 Project Showcases.

Each project demonstrates a different workflow shape, domain, and set of
LARGESTACK capabilities. All exports are real Studio HTML rendered from the
production framework — open any in a browser to see the same big-graph
audit-rich UI for ten very different agent applications.

Run from project root:  python examples/showcase/ten_projects.py
"""

from __future__ import annotations
import asyncio
import time
from pathlib import Path

from largestack._studio import (
    StudioBuilder,
    NodeSpec,
    EdgeSpec,
    MemorySnapshot,
    ComplianceMarker,
)


OUT_DIR = Path("/mnt/user-data/outputs")


# ---------------------------------------------------------------------------
# Helpers — keep each project's code small by sharing builders
# ---------------------------------------------------------------------------


def add_nodes(b: StudioBuilder, specs):
    """specs: list of (id, label, kind)"""
    for nid, label, kind in specs:
        b.add_node(NodeSpec(id=nid, label=label, kind=kind))


def add_edges(b: StudioBuilder, edges):
    """edges: list of (source, target)"""
    for s, t in edges:
        b.add_edge(EdgeSpec(source=s, target=t))


def add_events(b: StudioBuilder, events, tenant: str):
    """events: list of (agent, event, payload, duration_ms)"""
    for agent, event, payload, dur in events:
        b.add_audit_event(
            agent=agent,
            event=event,
            payload=payload,
            duration_ms=float(dur),
            tenant_id=tenant,
        )


def add_compliance(b: StudioBuilder, markers):
    """markers: list of (name, section, notes)"""
    for name, section, notes in markers:
        b.add_compliance(
            ComplianceMarker(
                name=name,
                section=section,
                notes=notes,
            )
        )


# ---------------------------------------------------------------------------
# 1. Sri Rajeshwari Gold Loan NBFC — KYC + disbursement (DAG)
# ---------------------------------------------------------------------------


def project_1_gold_loan_nbfc() -> StudioBuilder:
    b = StudioBuilder(
        title="Sri Rajeshwari Gold Loan NBFC — KYC & Disbursement",
        description=(
            "End-to-end loan origination for a 12-branch gold-loan NBFC. "
            "Customer walks in with ornaments, gets KYC'd, gold valued, "
            "loan disbursed via Razorpay — DPDP/RBI compliant throughout."
        ),
    )
    add_nodes(
        b,
        [
            ("intake", "Customer Intake", "start"),
            ("aadhaar", "Aadhaar OKYC", "tool"),
            ("pan", "PAN Verify", "tool"),
            ("digilocker", "DigiLocker Pull", "tool"),
            ("cibil", "CIBIL Bureau Pull", "tool"),
            ("gold_val", "Gold Valuation Agent", "agent"),
            ("ltv", "LTV Calculator", "agent"),
            ("risk", "Risk Scorer", "agent"),
            ("decide", "Approve / Reject", "decision"),
            ("esign", "Leegality eSign", "tool"),
            ("disburse", "Razorpay Disbursement", "tool"),
            ("audit", "Hash-Chain Audit", "tool"),
            ("notify", "Customer Notify", "tool"),
            ("done", "Loan Active", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("intake", "aadhaar"),
            ("intake", "pan"),
            ("intake", "digilocker"),
            ("aadhaar", "cibil"),
            ("pan", "cibil"),
            ("digilocker", "gold_val"),
            ("cibil", "ltv"),
            ("gold_val", "ltv"),
            ("ltv", "risk"),
            ("risk", "decide"),
            ("decide", "esign"),
            ("esign", "disburse"),
            ("disburse", "audit"),
            ("audit", "notify"),
            ("notify", "done"),
        ],
    )

    tenant = "sri-rajeshwari-davangere-001"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="branch-davangere-mg-road",
            core_count=2,
            recall_count=12,
            archival_count=4827,
            core_block_preview=(
                "[branch] Davangere MG Road, gold-loan specialist\n"
                "[constraints] DPDP §6/§11, RBI MD-NBFC-D, PMLA Rule 9, "
                "8-year retention on KYC, 22ct purity standard"
            ),
        )
    )

    t0 = time.time()
    add_events(
        b,
        [
            ("intake", "customer.walked_in", {"channel": "branch_walk_in", "language": "kn"}, 12),
            (
                "aadhaar-okyc",
                "uidai.verified",
                {"masked": "XXXX XXXX 7821", "matched_name": True, "agent": "signzy"},
                320,
            ),
            (
                "pan-verify",
                "income_tax.verified",
                {"masked": "AAA***1C", "type": "individual"},
                180,
            ),
            (
                "digilocker",
                "documents.fetched",
                {"docs": ["aadhaar_xml", "pan_card", "voter_id"], "count": 3},
                420,
            ),
            ("cibil-pull", "bureau.scored", {"score": 712, "tier": "A", "open_loans": 1}, 850),
            (
                "gold-valuation",
                "ornaments.valued",
                {
                    "weight_g": 48.6,
                    "purity_ct": 22,
                    "rate_per_g_inr": 6280,
                    "gross_value_inr": 305208,
                },
                240,
            ),
            (
                "ltv-calculator",
                "ltv.computed",
                {"max_ltv_pct": 75, "loanable_inr": 228906, "rbi_cap_check": "passed"},
                35,
            ),
            (
                "risk-scorer",
                "risk.scored",
                {
                    "score": 0.18,
                    "risk_band": "low",
                    "reasons": ["good_cibil", "first_time_borrower_at_branch"],
                },
                95,
            ),
            (
                "decision-agent",
                "loan.approved",
                {"amount_inr": 200000, "tenure_months": 12, "interest_pct": 13.5},
                18,
            ),
            (
                "leegality-esign",
                "agreement.signed",
                {"document_id": "AGR-2026-0421-098", "ip_hash": "0x7af3c1", "stamp_paid_inr": 200},
                1820,
            ),
            (
                "razorpay-disburse",
                "transfer.captured",
                {
                    "amount_inr": 200000,
                    "payment_id": "pay_QrMn7vXz",
                    "settlement": "T+1",
                    "status": "captured",
                },
                920,
            ),
            (
                "hash-chain-audit",
                "ledger.appended",
                {"position": 84273, "merkle": "0xa9f4...", "events": 11},
                8,
            ),
            (
                "notify-agent",
                "sms.sent",
                {"channel": "MSG91", "language": "kn", "template": "loan_approved_kn"},
                120,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("DPDP_Act_2023", "Section 6", "purpose: loan_underwriting"),
            ("DPDP_Act_2023", "Section 7", "lawful basis: contract"),
            ("DPDP_Act_2023", "Section 11", "right-to-erasure honored"),
            ("RBI MD-NBFC-D", "Annex IV", "data segregation"),
            ("RBI Master IRACP", "Para 2", "income recognition + provisioning"),
            ("PMLA Rule 9", "CDD", "customer due diligence captured"),
            ("PMLA Rule 9", "EDD", "PEP screening: clear"),
            ("IT Act 2000", "Section 43A", "reasonable security practices"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 2. LegalDocs.in — 96-template legal document Q&A (RAG sequential)
# ---------------------------------------------------------------------------


def project_2_legaldocs() -> StudioBuilder:
    b = StudioBuilder(
        title="LegalDocs.in — Indian Legal Document Q&A",
        description=(
            "Lawyer uploads a 200-page MSA. LARGESTACK chunks, embeds, "
            "answers clause-level questions with citations — all under "
            "DPDP §7 legitimate use."
        ),
    )
    add_nodes(
        b,
        [
            ("upload", "Doc Upload (PDF)", "start"),
            ("ocr", "LlamaParse OCR", "tool"),
            ("chunk", "Semantic Chunker", "agent"),
            ("embed", "Bedrock Embeddings", "agent"),
            ("vector", "Qdrant Index", "tool"),
            ("question", "Lawyer's Question", "checkpoint"),
            ("retriever", "Hybrid Retrieval", "agent"),
            ("rerank", "Cohere Rerank", "tool"),
            ("synthesize", "Synthesis Agent", "agent"),
            ("citation", "Citation Builder", "agent"),
            ("guardrail", "PII Redact Guard", "agent"),
            ("respond", "Lawyer's Reply", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("upload", "ocr"),
            ("ocr", "chunk"),
            ("chunk", "embed"),
            ("embed", "vector"),
            ("question", "retriever"),
            ("vector", "retriever"),
            ("retriever", "rerank"),
            ("rerank", "synthesize"),
            ("synthesize", "citation"),
            ("citation", "guardrail"),
            ("guardrail", "respond"),
        ],
    )

    tenant = "legaldocs-firm-bangalore-007"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="advocate-suresh-rao",
            core_count=3,
            recall_count=42,
            archival_count=14_280,
            core_block_preview=(
                "[firm] Bangalore corporate-law boutique\n"
                "[active_matters] 12 ongoing M&A, 4 IPR disputes\n"
                "[prefs] always cite section + clause; conservative tone"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "upload-handler",
                "file.received",
                {"filename": "TVS-MotorBoatYard-MSA-v3.pdf", "size_mb": 4.7, "pages": 187},
                18,
            ),
            (
                "llamaparse",
                "ocr.complete",
                {"text_chars": 412_000, "tables": 23, "images": 41},
                8420,
            ),
            (
                "semantic-chunker",
                "chunks.created",
                {"chunks": 312, "avg_tokens": 480, "method": "semantic_breakpoint"},
                1240,
            ),
            (
                "bedrock-embed",
                "vectors.computed",
                {
                    "model": "cohere-embed-multilingual-v3",
                    "dim": 1024,
                    "region": "ap-south-1",
                    "cost_usd": 0.041,
                },
                4180,
            ),
            ("qdrant", "index.populated", {"collection": "msa_corpus_v3", "vectors": 312}, 220),
            (
                "question-handler",
                "query.received",
                {"question": "What is the indemnity cap and how is it carved out?"},
                5,
            ),
            (
                "hybrid-retriever",
                "results.fused",
                {
                    "vector_hits": 8,
                    "bm25_hits": 12,
                    "rrf_top_k": 5,
                    "method": "reciprocal_rank_fusion",
                },
                380,
            ),
            (
                "cohere-rerank",
                "reranked",
                {"model": "rerank-english-v3.0", "top_k": 3, "top_score": 0.94},
                410,
            ),
            (
                "synthesis-agent",
                "answer.drafted",
                {"clause_refs": ["14.3", "14.4", "Sch-D"], "draft_chars": 1840, "verified": True},
                2840,
            ),
            (
                "citation-builder",
                "citations.attached",
                {"count": 4, "format": "bluebook_indian_modified"},
                95,
            ),
            ("pii-guard", "scan.complete", {"patterns_redacted": 0, "verified": True}, 22),
            (
                "respond-handler",
                "delivery.sent",
                {"channel": "web_ui", "char_count": 1840, "tokens_used": 4220},
                14,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("DPDP_Act_2023", "Section 7", "lawful basis: legitimate_use"),
            ("DPDP_Act_2023", "Section 6", "purpose: legal_research"),
            ("Bar Council of India", "Rules", "advocate confidentiality maintained"),
            ("IT Act 2000", "Section 43A", "reasonable security"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 3. Halliburton RTA Type-A Markup — engineering DAG
# ---------------------------------------------------------------------------


def project_3_halliburton_rta() -> StudioBuilder:
    b = StudioBuilder(
        title="Halliburton RTA Type-A Markup — Quest Global",
        description=(
            "Request for Technical Authorization automation. Type A = "
            "dimensional/length changes to existing oilfield parts. "
            "7-stage agentic pipeline → CAD layer → CWI portal export."
        ),
    )
    add_nodes(
        b,
        [
            ("rta_in", "RTA Case Intake", "start"),
            ("classify", "Type-A Classifier", "agent"),
            ("qp_extract", "QP Extractor", "agent"),
            ("dsd_pull", "DSD Sheet Lookup", "tool"),
            ("bom_build", "BOM Builder", "agent"),
            ("dim_calc", "Dimensional Calc", "agent"),
            ("rule_check", "Rule Validator (42)", "agent"),
            ("cad_handoff", "CAD Engine Handoff", "tool"),
            ("review", "Engineer Review", "checkpoint"),
            ("approve", "Approve / Rework", "decision"),
            ("cwi_export", "CWI Portal Export", "tool"),
            ("audit", "Halliburton Audit", "tool"),
            ("close", "RTA Closed", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("rta_in", "classify"),
            ("classify", "qp_extract"),
            ("qp_extract", "dsd_pull"),
            ("dsd_pull", "bom_build"),
            ("bom_build", "dim_calc"),
            ("dim_calc", "rule_check"),
            ("rule_check", "cad_handoff"),
            ("cad_handoff", "review"),
            ("review", "approve"),
            ("approve", "cwi_export"),
            ("cwi_export", "audit"),
            ("audit", "close"),
        ],
    )

    tenant = "halliburton-quest-global-rta-prod"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="rta-eng-pramod-shenoy",
            core_count=4,
            recall_count=128,
            archival_count=72_440,
            core_block_preview=(
                "[customer] Halliburton via Quest Global\n"
                "[mvp_phase] MVP1, scope: Type A only (24 of 70 functions)\n"
                "[architecture] K3S + Gateway API + KEDA + CPU agents + GPU Ollama"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "rta-intake",
                "case.received",
                {"rta_id": "RTA-2026-04-1247", "drawing": "DWG-78421-RevC.pdf"},
                24,
            ),
            (
                "type-classifier",
                "type_a.confirmed",
                {"confidence": 0.97, "category": "dimensional", "fallback_required": False},
                380,
            ),
            (
                "qp-extractor",
                "params.extracted",
                {
                    "length_change_mm": 18,
                    "diameter_unchanged": True,
                    "thread_spec": "API_4-1/2_Reg",
                },
                1240,
            ),
            (
                "dsd-lookup",
                "sheet.found",
                {"part_no": "P-45821-A", "rev": "C", "geometry_file": "geom_p45821a_revC.step"},
                220,
            ),
            (
                "bom-builder",
                "bom.assembled",
                {"items": 14, "subassemblies": 3, "verified": True},
                480,
            ),
            (
                "dimensional-calc",
                "tolerances.computed",
                {"thread_pitch_ok": True, "stress_below_yield": True, "torque_rated_kn_m": 142},
                1820,
            ),
            (
                "rule-validator",
                "rules.evaluated",
                {"total_rules": 42, "passed": 42, "warnings": 0, "verified": True},
                720,
            ),
            (
                "cad-handoff",
                "step_file.delivered",
                {"engine": "Siemens NX", "version": "2406", "out_file": "P-45821-A-Rev-D.step"},
                4820,
            ),
            (
                "review-checkpoint",
                "engineer.reviewing",
                {"reviewer": "pramod-shenoy", "queue_position": 3},
                0,
            ),
            (
                "approve-decision",
                "rev_d.approved",
                {"reason": "all checks pass, no carryover risk", "verified": True},
                32,
            ),
            (
                "cwi-export",
                "package.uploaded",
                {"target": "https://cwi.halliburton.com/portal", "files": 5, "size_mb": 18.4},
                2840,
            ),
            (
                "halliburton-audit",
                "audit.recorded",
                {"approver": "pramod-shenoy", "case_state": "CLOSED", "automation_pct": 87.4},
                45,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("ISO 9001", "Quality Mgmt", "review checkpoint enforced"),
            ("API Spec 5CT", "OCTG", "thread integrity verified"),
            ("Halliburton ITAR", "export_control", "no foreign person access during run"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 4. CA Practice Platform — GST + ITR mass workflow (parallel)
# ---------------------------------------------------------------------------


def project_4_ca_platform() -> StudioBuilder:
    b = StudioBuilder(
        title="CA Practice Platform — GST + ITR Mass Filing",
        description=(
            "CA firm onboards 50 SMB clients in October. LARGESTACK "
            "spawns parallel agents per client, validates, files, "
            "tracks ITC mismatches — all in one weekend instead of three."
        ),
    )
    add_nodes(
        b,
        [
            ("clients", "50 Clients Queue", "start"),
            ("split", "Per-Client Splitter", "agent"),
            ("c1", "Client A: GST 3B", "agent"),
            ("c2", "Client B: GST 1", "agent"),
            ("c3", "Client C: ITR-3", "agent"),
            ("c_dots", "...47 more clients", "agent"),
            ("itc", "ITC Reconciler", "agent"),
            ("validate", "Schema Validator", "agent"),
            ("portal", "GSTN / IT Portal", "tool"),
            ("ack", "Acknowledgement", "tool"),
            ("notify", "Client SMS+Email", "tool"),
            ("done", "Filing Complete", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("clients", "split"),
            ("split", "c1"),
            ("split", "c2"),
            ("split", "c3"),
            ("split", "c_dots"),
            ("c1", "itc"),
            ("c2", "itc"),
            ("c3", "itc"),
            ("c_dots", "itc"),
            ("itc", "validate"),
            ("validate", "portal"),
            ("portal", "ack"),
            ("ack", "notify"),
            ("notify", "done"),
        ],
    )

    tenant = "ca-firm-rao-associates-bangalore"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="ca-rao-firm",
            core_count=3,
            recall_count=412,
            archival_count=58_240,
            core_block_preview=(
                "[firm] Rao & Associates, Bengaluru, ICAI 124871\n"
                "[clients] 197 active, 50 in this batch\n"
                "[icai_compliance] code of ethics 2020, Cl 4 — confidentiality"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "queue-handler",
                "batch.started",
                {"clients": 50, "filing_period": "Oct-2026", "type": "GSTR-3B+ITR-3"},
                12,
            ),
            ("splitter", "fan_out.complete", {"parallelism": 50, "max_concurrent": 8}, 240),
            (
                "agent-client-A",
                "books.fetched",
                {"client_id": "RAO-C-018", "tally_records": 4280},
                1820,
            ),
            (
                "agent-client-B",
                "books.fetched",
                {"client_id": "RAO-C-024", "zoho_records": 1240},
                1240,
            ),
            (
                "itc-reconciler",
                "mismatch.detected",
                {"client_id": "RAO-C-018", "mismatch_count": 3, "warning": "3 invoices not in 2A"},
                320,
            ),
            ("itc-reconciler", "reconciled", {"matched": 47, "unmatched_flagged": 3}, 480),
            ("schema-validator", "all.passed", {"clients_validated": 50, "errors": 0}, 1240),
            ("gstn-portal", "filed", {"acknowledgement_count": 50, "all_arn_received": True}, 8420),
            (
                "notify-agent",
                "sms_email.batch",
                {"sms_sent": 50, "email_sent": 50, "channel": "MSG91+SES"},
                1820,
            ),
            (
                "audit-emit",
                "filing_log.sealed",
                {"clients": 50, "challans": 50, "icai_log": True},
                32,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("CGST Act 2017", "Section 39", "monthly return filing"),
            ("CGST Act 2017", "Section 16", "ITC eligibility check"),
            ("Income Tax Act 1961", "Section 139", "ITR filing"),
            ("ICAI Code of Ethics", "Cl 4", "client confidentiality"),
            ("DPDP_Act_2023", "Section 7", "lawful basis: legal_obligation"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 5. Granite ERP — quote-to-cash (sequential business process)
# ---------------------------------------------------------------------------


def project_5_granite_erp() -> StudioBuilder:
    b = StudioBuilder(
        title="Granite ERP — Quote to Cash (export consignment)",
        description=(
            "South-Indian granite trader receives RFQ from Italian buyer. "
            "LARGESTACK orchestrates inventory check, slab matching, "
            "quote, export docs, port logistics, and Razorpay-Italy via "
            "ERPNext."
        ),
    )
    add_nodes(
        b,
        [
            ("rfq", "Italian Buyer RFQ", "start"),
            ("translate", "Translate (EN↔IT)", "agent"),
            ("inventory", "Slab Inventory Match", "agent"),
            ("price", "Pricing Engine", "agent"),
            ("quote", "Quote Generator", "agent"),
            ("approval", "Buyer Approval", "checkpoint"),
            ("docs", "Export Docs Builder", "agent"),
            ("shipping", "DGFT + Customs", "tool"),
            ("logistics", "Port Logistics", "tool"),
            ("razorpay", "Razorpay Italy", "tool"),
            ("erpnext", "ERPNext Invoice", "tool"),
            ("audit", "Audit Trail", "tool"),
            ("close", "Order Closed", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("rfq", "translate"),
            ("translate", "inventory"),
            ("inventory", "price"),
            ("price", "quote"),
            ("quote", "approval"),
            ("approval", "docs"),
            ("docs", "shipping"),
            ("shipping", "logistics"),
            ("logistics", "razorpay"),
            ("razorpay", "erpnext"),
            ("erpnext", "audit"),
            ("audit", "close"),
        ],
    )

    tenant = "granite-orient-stones-bangalore"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="export-mgr-suresh",
            core_count=3,
            recall_count=89,
            archival_count=12_840,
            core_block_preview=(
                "[firm] Orient Stones Pvt Ltd, Bengaluru\n"
                "[markets] Italy, US, UAE, Saudi, EU\n"
                "[product] granite slabs, 3cm/2cm, polished/leather"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "rfq-handler",
                "rfq.received",
                {
                    "buyer": "Marmi Italia SRL",
                    "country": "IT",
                    "request": "20 slabs Absolute Black 3cm polished",
                },
                18,
            ),
            ("translate-agent", "translated", {"src": "it", "tgt": "en", "tokens": 412}, 380),
            (
                "inventory-matcher",
                "slabs.found",
                {"matched": 23, "block_id": "AB-2026-082", "gangsaw_block": "yes"},
                920,
            ),
            (
                "pricing-agent",
                "quoted",
                {"unit_inr": 4280, "total_inr": 856000, "incoterm": "CIF Genova", "margin_pct": 32},
                240,
            ),
            (
                "quote-generator",
                "pdf.built",
                {"format": "PDF/A", "template": "EU_export_v3", "languages": ["en", "it"]},
                480,
            ),
            (
                "buyer-approval",
                "approved",
                {"signed_via": "DocuSign EU", "buyer_signer": "M. Conti"},
                0,
            ),
            (
                "export-docs",
                "package.assembled",
                {
                    "docs": [
                        "commercial_invoice",
                        "packing_list",
                        "certificate_of_origin",
                        "phytosanitary",
                    ]
                },
                1820,
            ),
            (
                "dgft-customs",
                "shipping_bill.filed",
                {"shipping_bill_no": "SB-2026-043281", "ice_gate_ack": True},
                4280,
            ),
            (
                "port-logistics",
                "container.booked",
                {"port": "Chennai", "carrier": "MSC", "container_type": "20'OT"},
                920,
            ),
            (
                "razorpay-it",
                "advance.captured",
                {"amount_eur": 9200, "fx_inr_rate": 91.4, "payment_id": "rzp_eu_K9p4mNx"},
                1240,
            ),
            (
                "erpnext",
                "invoice.posted",
                {"invoice_no": "EX-INV-2026-0421", "gst_export": "0% (LUT)", "tax_inr": 0},
                320,
            ),
            ("audit-emit", "trade.audited", {"events": 11, "rbi_export_code": "082001"}, 12),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("FEMA 1999", "Sec 7", "export of goods, RBI guidelines"),
            ("Customs Act 1962", "Sec 50", "shipping bill"),
            ("CGST Act 2017", "Sec 16(3)", "export under LUT, no GST"),
            ("DGFT FTP", "Chapter 2", "IEC code 0987654321"),
            ("DPDP_Act_2023", "Section 7", "basis: contract"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 6. AstroCoach — multi-system astrology composite (swarm)
# ---------------------------------------------------------------------------


def project_6_astrocoach() -> StudioBuilder:
    b = StudioBuilder(
        title="AstroCoach — Multi-System Composite Reading",
        description=(
            "User asks 'what's my year ahead?'. LARGESTACK runs Vedic, "
            "Western, and Chinese systems in parallel via swarm pattern, "
            "synthesises, and delivers in user's preferred language."
        ),
    )
    add_nodes(
        b,
        [
            ("intake", "User Birth Details", "start"),
            ("normalize", "TZ + Geo Normalizer", "agent"),
            ("ephemeris", "Swiss Ephemeris (SIDE)", "tool"),
            ("vedic", "Vedic Agent", "agent"),
            ("western", "Western Agent", "agent"),
            ("chinese", "Chinese Agent", "agent"),
            ("numerology", "Numerology Agent", "agent"),
            ("supervisor", "Synthesis Supervisor", "agent"),
            ("language", "Hindi/En/Ta/Te Trans", "agent"),
            ("guardrail", "Wellbeing Guardrail", "agent"),
            ("deliver", "Reading Delivered", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("intake", "normalize"),
            ("normalize", "ephemeris"),
            ("ephemeris", "vedic"),
            ("ephemeris", "western"),
            ("ephemeris", "chinese"),
            ("ephemeris", "numerology"),
            ("vedic", "supervisor"),
            ("western", "supervisor"),
            ("chinese", "supervisor"),
            ("numerology", "supervisor"),
            ("supervisor", "language"),
            ("language", "guardrail"),
            ("guardrail", "deliver"),
        ],
    )

    tenant = "astrocoach-app-pro-tier"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="user-aaditi-1994-mumbai",
            core_count=4,
            recall_count=22,
            archival_count=1_240,
            core_block_preview=(
                "[user] DOB 1994-03-15 04:32 IST, Mumbai\n"
                "[ascendant] Capricorn (Vedic Makara)\n"
                "[prefs] Hindi reading, no dire predictions, focus on career"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "intake",
                "details.received",
                {"dob": "1994-03-15", "tob": "04:32", "place": "Mumbai"},
                8,
            ),
            (
                "tz-normalizer",
                "utc.computed",
                {"local_iso": "1994-03-14T23:02:00Z", "lat": 19.0760, "lon": 72.8777},
                18,
            ),
            (
                "swiss-ephemeris",
                "positions.computed",
                {"system": "Lahiri (sidereal)", "ayanamsa_deg": 23.83, "planets_count": 9},
                240,
            ),
            (
                "vedic-agent",
                "chart.read",
                {
                    "lagna": "Capricorn",
                    "moon_sign": "Sagittarius",
                    "current_dasha": "Mercury MD/Saturn AD",
                },
                1240,
            ),
            (
                "western-agent",
                "chart.read",
                {"sun": "Pisces 25°", "moon": "Sagittarius 12°", "rising": "Aquarius"},
                1180,
            ),
            (
                "chinese-agent",
                "chart.read",
                {"year_animal": "Dog (1994 Yang Wood)", "element_balance": "balanced"},
                940,
            ),
            (
                "numerology-agent",
                "numbers.computed",
                {"life_path": 5, "destiny": 8, "name_score": 7.4},
                320,
            ),
            (
                "synthesis-supervisor",
                "composite.drafted",
                {
                    "agreement_score": 0.78,
                    "themes": ["career_change", "relocation", "creative_success"],
                },
                2840,
            ),
            (
                "language-translator",
                "translated_to_hi",
                {"src": "en", "tgt": "hi", "tone": "warm_supportive", "tokens": 1820},
                1420,
            ),
            (
                "wellbeing-guardrail",
                "filtered",
                {"removed_phrases": 2, "reason": "fatalistic_language", "verified": True},
                95,
            ),
            (
                "deliver",
                "reading.sent",
                {"channel": "in_app_pdf+audio", "audio_minutes": 12, "tts_voice": "alloy_hi"},
                4820,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("DPDP_Act_2023", "Section 6", "purpose: personalisation_consented"),
            ("DPDP_Act_2023", "Section 8", "no profiling decisions"),
            ("Mental Health Act 2017", "Sec 18", "no medical claim language"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 7. RBIH Mule Hunter — fraud detection (router pattern)
# ---------------------------------------------------------------------------


def project_7_mule_hunter() -> StudioBuilder:
    b = StudioBuilder(
        title="RBIH Mule Hunter — Fraud Detection Pipeline",
        description=(
            "Real-time mule-account detection for PNB + HDFC. UPI/IMPS "
            "transactions stream in. Router picks the right specialist "
            "per signal (graph, behavioral, device). Flags within 200ms."
        ),
    )
    add_nodes(
        b,
        [
            ("txn", "UPI/IMPS Stream", "start"),
            ("ingest", "Kafka Ingestor", "tool"),
            ("enrich", "Enrichment Agent", "agent"),
            ("router", "Signal Router", "agent"),
            ("graph", "Graph Specialist", "agent"),
            ("behav", "Behavioral Specialist", "agent"),
            ("device", "Device Fingerprint", "agent"),
            ("score", "Risk Score Aggregator", "agent"),
            ("threshold", "Threshold Check", "decision"),
            ("escalate", "FIU-IND Escalation", "tool"),
            ("freeze", "Account Freeze", "tool"),
            ("audit", "RBI Audit Sink", "tool"),
            ("cleared", "Allowed", "end"),
            ("blocked", "Blocked + Reported", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("txn", "ingest"),
            ("ingest", "enrich"),
            ("enrich", "router"),
            ("router", "graph"),
            ("router", "behav"),
            ("router", "device"),
            ("graph", "score"),
            ("behav", "score"),
            ("device", "score"),
            ("score", "threshold"),
            ("threshold", "cleared"),
            ("threshold", "escalate"),
            ("escalate", "freeze"),
            ("freeze", "audit"),
            ("audit", "blocked"),
        ],
    )

    tenant = "rbih-pnb-mule-hunter-prod"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="mule-hunter-shard-12",
            core_count=2,
            recall_count=2_450,
            archival_count=18_400_000,
            core_block_preview=(
                "[bank] PNB + HDFC pilot\n"
                "[scale] 4M txns/day, 18.4M historical accounts\n"
                "[sla] p99 < 200ms, FIU-IND notify within 7 working days"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "kafka",
                "txn.consumed",
                {"txn_id": "UPI-2026-04-21-T-094128", "amount_inr": 45000, "type": "upi_p2p"},
                4,
            ),
            (
                "enrich-agent",
                "enriched",
                {
                    "sender_account_age_days": 12,
                    "receiver_account_age_days": 8,
                    "kyc_match_pct": 100,
                },
                18,
            ),
            (
                "signal-router",
                "specialists.dispatched",
                {"selected": ["graph", "behavioral", "device"], "skipped": ["cibil"]},
                6,
            ),
            (
                "graph-specialist",
                "subgraph.scored",
                {
                    "distance_from_known_mule": 2,
                    "node_centrality": 0.84,
                    "warning": "high centrality, 2 hops from prior mule",
                },
                42,
            ),
            (
                "behavioral-specialist",
                "anomaly.detected",
                {"velocity_z": 4.2, "amount_z": 3.1, "warning": "velocity 4.2σ above baseline"},
                28,
            ),
            (
                "device-fingerprint",
                "device.flagged",
                {
                    "emulator": True,
                    "gps_spoofed_likelihood": 0.91,
                    "warning": "emulator + spoofed GPS",
                },
                12,
            ),
            (
                "score-aggregator",
                "risk.combined",
                {"composite_score": 0.87, "tier": "high", "warning": "exceeds threshold 0.75"},
                8,
            ),
            (
                "threshold-check",
                "block.triggered",
                {"threshold": 0.75, "actual": 0.87, "verified": False},
                4,
            ),
            (
                "fiu-escalation",
                "str.queued",
                {"str_template": "STR-AUTO-2026-04-Q21-T0941", "deadline_hours": 168},
                14,
            ),
            (
                "account-freeze",
                "freeze.applied",
                {
                    "account": "PNB-XXXX-9821",
                    "scope": "credit_block",
                    "approved_by": "auto_policy_v3",
                },
                18,
            ),
            (
                "rbi-audit",
                "report.queued",
                {"format": "RBI_FRAUD_v2.4", "submission_due": "next_quarter"},
                6,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("PMLA Rule 9", "STR", "suspicious transaction reported within 7 days"),
            ("RBI Master Direction", "Fraud", "frauds reporting framework 2016"),
            ("RBI Cyber Security", "GBA-IT 2017", "real-time monitoring"),
            ("DPDP_Act_2023", "Section 7", "basis: legal_obligation"),
            ("BSBDA Guidelines", "RBI", "no_freeze_without_due_process"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 8. Salon Personalisation — SaaS multi-tenant (light DAG)
# ---------------------------------------------------------------------------


def project_8_salon() -> StudioBuilder:
    b = StudioBuilder(
        title="GlowUp Studio — Salon Personalisation Agent",
        description=(
            "Customer books online. Agent recalls past services, suggests "
            "add-ons, optimises stylist match, and Razorpay charges — "
            "all tenant-isolated for the SaaS multi-salon platform."
        ),
    )
    add_nodes(
        b,
        [
            ("booking", "Customer Booking", "start"),
            ("identify", "Customer Lookup", "tool"),
            ("recall", "Past-Visit Recall", "agent"),
            ("preferences", "Preference Agent", "agent"),
            ("addon", "Add-on Recommender", "agent"),
            ("stylist", "Stylist Matcher", "agent"),
            ("schedule", "Slot Optimizer", "agent"),
            ("razorpay", "Razorpay Charge", "tool"),
            ("whatsapp", "WhatsApp Confirm", "tool"),
            ("done", "Booked", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("booking", "identify"),
            ("identify", "recall"),
            ("recall", "preferences"),
            ("preferences", "addon"),
            ("addon", "stylist"),
            ("stylist", "schedule"),
            ("schedule", "razorpay"),
            ("razorpay", "whatsapp"),
            ("whatsapp", "done"),
        ],
    )

    tenant = "glowup-salon-koramangala-04"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="customer-priya-9821",
            core_count=2,
            recall_count=18,
            archival_count=247,
            core_block_preview=(
                "[salon] GlowUp Koramangala 4th block\n"
                "[customer] Priya, 28 visits, prefers Anjali (stylist), "
                "loyalty tier Gold, allergic to ammonia"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "booking",
                "request.received",
                {"service": "haircut+color", "preferred_stylist": "anjali"},
                12,
            ),
            (
                "identify",
                "customer.found",
                {"customer_id": "C-9821", "loyalty": "Gold", "lifetime_value_inr": 24800},
                22,
            ),
            (
                "recall-agent",
                "past.recalled",
                {
                    "last_visit_days_ago": 42,
                    "last_color": "burgundy_brown",
                    "favorite_addon": "head_massage_15min",
                },
                95,
            ),
            (
                "preference-agent",
                "matched",
                {"avoid": ["ammonia"], "preferred_brand": "schwarzkopf"},
                32,
            ),
            (
                "addon-recommender",
                "suggested",
                {"addons": ["head_massage", "deep_conditioning"], "expected_uplift_inr": 1100},
                240,
            ),
            (
                "stylist-matcher",
                "matched",
                {"stylist": "anjali", "available": True, "rating_pair_score": 0.96},
                45,
            ),
            (
                "slot-optimizer",
                "scheduled",
                {"slot": "2026-04-23 16:30", "duration_min": 95, "buffer_min": 15},
                18,
            ),
            (
                "razorpay",
                "advance.captured",
                {"amount_inr": 800, "type": "booking_deposit", "payment_id": "pay_QwAnj4mPx"},
                820,
            ),
            (
                "whatsapp",
                "confirmation.sent",
                {"channel": "Meta WABA", "template": "booking_confirm_v3", "language": "en"},
                240,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("DPDP_Act_2023", "Section 6", "purpose: service_personalisation"),
            ("DPDP_Act_2023", "Section 11", "right-to-erasure honored"),
            ("Consumer Protection Act 2019", "Sec 2(34)", "service standards declared"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 9. Bill of Lading Automation — customs broker DAG with HITL
# ---------------------------------------------------------------------------


def project_9_bl_automation() -> StudioBuilder:
    b = StudioBuilder(
        title="B/L Automation — Indian Customs Broker",
        description=(
            "Customs broker uploads shipping documents. LARGESTACK "
            "OCRs, validates, pre-flags ICEGATE errors, and routes "
            "exceptions to a human operator before filing."
        ),
    )
    add_nodes(
        b,
        [
            ("upload", "Doc Pack Upload", "start"),
            ("ocr", "Doc AI OCR", "tool"),
            ("classify", "Doc Classifier", "agent"),
            ("extract", "Field Extractor", "agent"),
            ("validate", "ICEGATE Pre-Validator", "agent"),
            ("error", "Error Detector", "agent"),
            ("hitl", "Human Reviewer", "checkpoint"),
            ("correct", "Field Corrector", "agent"),
            ("submit", "ICEGATE Submit", "tool"),
            ("ack", "BoE Acknowledgement", "tool"),
            ("audit", "Customs Audit Log", "tool"),
            ("done", "Cleared", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("upload", "ocr"),
            ("ocr", "classify"),
            ("classify", "extract"),
            ("extract", "validate"),
            ("validate", "error"),
            ("error", "hitl"),
            ("hitl", "correct"),
            ("correct", "submit"),
            ("submit", "ack"),
            ("ack", "audit"),
            ("audit", "done"),
        ],
    )

    tenant = "vinod-customs-clearing-mumbai"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="cb-vinod-shah",
            core_count=2,
            recall_count=240,
            archival_count=18_240,
            core_block_preview=(
                "[broker] Vinod Customs Clearing, JNPT Mumbai\n"
                "[license] CHA No. R-AB-184/2018\n"
                "[avg_volume] 80 BoEs/month"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "upload",
                "pack.received",
                {"docs": ["invoice", "packing_list", "B/L"], "size_mb": 14.2},
                18,
            ),
            (
                "doc-ai-ocr",
                "extracted",
                {"engine": "google_document_ai", "confidence": 0.94, "tables": 4},
                4280,
            ),
            (
                "classifier",
                "categorised",
                {"importer_type": "trader", "hs_code_predicted": "73181500", "verified": True},
                220,
            ),
            (
                "field-extractor",
                "extracted",
                {
                    "fields_extracted": 41,
                    "missing": 2,
                    "warning": "country_of_origin_certificate not found",
                },
                480,
            ),
            (
                "icegate-validator",
                "rules.checked",
                {
                    "rules_passed": 27,
                    "rules_warnings": 2,
                    "warning": "potential ITC restriction on hs_code 73181500",
                },
                320,
            ),
            (
                "error-detector",
                "issues.flagged",
                {
                    "severity": "medium",
                    "warning": "HS classification ambiguous between 7318 and 7320",
                },
                95,
            ),
            (
                "human-checkpoint",
                "queued",
                {"reviewer": "cb-vinod-shah", "queue_position": 1, "wait_minutes_estimated": 2.4},
                0,
            ),
            (
                "field-corrector",
                "applied",
                {"hs_code_corrected": "73181500", "verified": True, "approved_by": "cb-vinod-shah"},
                0,
            ),
            (
                "icegate",
                "boe.filed",
                {"boe_no": "BoE-2026-04-21-08247", "challan": "CHN-2026-44128"},
                6240,
            ),
            (
                "acknowledgement",
                "received",
                {"icegate_ack_no": "ACK-2026-082-7128", "status": "PASSED_FIRST_CHECK"},
                240,
            ),
            (
                "customs-audit",
                "log.appended",
                {"events": 11, "audit_id": "CB-VS-2026-04-21-001"},
                22,
            ),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("Customs Act 1962", "Sec 46", "Bill of Entry filing"),
            ("Customs Act 1962", "Sec 50", "Shipping bill"),
            ("CBLR 2018", "Reg 10", "broker due diligence"),
            ("DPDP_Act_2023", "Section 7", "basis: legal_obligation"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# 10. Personal Productivity Jarvis — at-home agent (light supervisor)
# ---------------------------------------------------------------------------


def project_10_jarvis_personal() -> StudioBuilder:
    b = StudioBuilder(
        title="Jarvis Personal — Home Office Assistant",
        description=(
            "Single-user productivity agent that summarises emails, "
            "drafts replies, books focus blocks, and silences "
            "notifications during deep work — entirely on-device."
        ),
    )
    add_nodes(
        b,
        [
            ("voice", "Voice Trigger", "start"),
            ("transcribe", "Whisper Transcribe", "tool"),
            ("intent", "Intent Router", "agent"),
            ("calendar", "Calendar Skill", "agent"),
            ("email", "Email Skill", "agent"),
            ("focus", "Focus Mode Skill", "agent"),
            ("smart_home", "Home Automation", "tool"),
            ("memory", "Personal Memory", "tool"),
            ("synthesise", "Reply Composer", "agent"),
            ("tts", "TTS Voice Reply", "tool"),
            ("done", "Done", "end"),
        ],
    )
    add_edges(
        b,
        [
            ("voice", "transcribe"),
            ("transcribe", "intent"),
            ("intent", "calendar"),
            ("intent", "email"),
            ("intent", "focus"),
            ("calendar", "memory"),
            ("email", "memory"),
            ("focus", "smart_home"),
            ("memory", "synthesise"),
            ("smart_home", "synthesise"),
            ("synthesise", "tts"),
            ("tts", "done"),
        ],
    )

    tenant = "personal-jarvis-sachith-home"
    b.set_memory_snapshot(
        MemorySnapshot(
            tenant_id=tenant,
            user_id="sachith",
            core_count=4,
            recall_count=128,
            archival_count=4_240,
            core_block_preview=(
                "[user] Sachith, RivaiLabs founder\n"
                "[deep_work] 22:00–01:00 IST every weeknight\n"
                "[prefs] terse, no emojis, code blocks for code, dark mode"
            ),
        )
    )

    add_events(
        b,
        [
            (
                "wake-trigger",
                "voice.detected",
                {"phrase": "Jarvis, what's pending?", "snr_db": 24},
                18,
            ),
            (
                "whisper",
                "transcribed",
                {"model": "whisper-large-v3-turbo", "language": "en", "duration_ms": 1420},
                1420,
            ),
            (
                "intent-router",
                "classified",
                {
                    "primary_intent": "summary_request",
                    "secondary": ["calendar", "email"],
                    "confidence": 0.94,
                },
                120,
            ),
            ("calendar-skill", "events.fetched", {"upcoming_today": 3, "free_blocks_h": 2.5}, 240),
            (
                "email-skill",
                "inbox.scanned",
                {"unread": 47, "important_count": 4, "summarised_subjects": 4},
                1820,
            ),
            (
                "focus-skill",
                "schedule.proposed",
                {"focus_block": "22:00-01:00", "do_not_disturb_active": True},
                18,
            ),
            (
                "smart-home",
                "config.applied",
                {"hue_dnd_active": True, "alexa_silent": True, "thermostat_setpoint_c": 22},
                480,
            ),
            (
                "personal-memory",
                "context.loaded",
                {"recent_topics": ["LARGESTACK_v1.0", "RTA_MVP1", "Granite_ERP_export"]},
                95,
            ),
            (
                "reply-composer",
                "drafted",
                {"length_words": 87, "tone": "terse_factual", "verified": True},
                1240,
            ),
            ("tts", "audio.played", {"voice": "alloy", "duration_s": 18.4}, 1240),
        ],
        tenant,
    )

    add_compliance(
        b,
        [
            ("Personal use", "n/a", "single-user, on-device, no DPDP scope"),
        ],
    )
    return b


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

PROJECTS = [
    ("01_gold_loan_nbfc", project_1_gold_loan_nbfc, "Sri Rajeshwari Gold Loan NBFC"),
    ("02_legaldocs", project_2_legaldocs, "LegalDocs.in RAG"),
    ("03_halliburton_rta", project_3_halliburton_rta, "Halliburton RTA Type-A Markup"),
    ("04_ca_platform", project_4_ca_platform, "CA Practice Platform — GST + ITR"),
    ("05_granite_erp", project_5_granite_erp, "Granite ERP Quote-to-Cash"),
    ("06_astrocoach", project_6_astrocoach, "AstroCoach Multi-System"),
    ("07_mule_hunter", project_7_mule_hunter, "RBIH Mule Hunter Fraud Detection"),
    ("08_salon_personalisation", project_8_salon, "GlowUp Salon Personalisation"),
    ("09_bl_automation", project_9_bl_automation, "B/L Automation Customs Broker"),
    ("10_jarvis_personal", project_10_jarvis_personal, "Jarvis Personal Productivity"),
]


async def main():
    print("=" * 70)
    print("  LARGESTACK — 10 Project Showcase")
    print("=" * 70)

    OUT_DIR.mkdir(exist_ok=True)
    for prefix, builder_fn, name in PROJECTS:
        b = builder_fn()
        path = OUT_DIR / f"showcase_{prefix}.html"
        b.export(path)
        payload = b.build_payload()
        size = path.stat().st_size
        print(f"\n  {prefix}: {name}")
        print(f"      nodes/edges: {len(payload['nodes'])}/{len(payload['edges'])}")
        print(f"      events:      {len(payload['audit'])}")
        print(f"      compliance:  {len(payload['compliance'])}")
        print(f"      file:        {path.name} ({size:,} B)")

    print(f"\n  ✅ All 10 projects rendered to {OUT_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
