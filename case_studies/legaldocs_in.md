# Case Study: LegalDocs.in

> India's first DPDP-aware legal document platform. 96 templates
> across 13 categories of Indian legal documents, all with proper
> Act citations + Indian English + state-specific stamp duty awareness.

## Problem

Indian legal document platforms have three structural gaps:

1. **US-centric language** — most use "check" instead of "cheque",
   "judgment" instead of "judgement", "willful" instead of "wilful"
2. **No Act citations** — drafts mention "the Companies Act" but not
   "Section 17 of the Indian Contract Act, 1872"
3. **No stamp duty awareness** — silent on Indian Stamp Act 1899
   obligations

These gaps don't just look amateur — they create real enforceability
risk for end users.

## Why LARGESTACK

LegalDocs.in evaluated:

| Stack | Verdict |
|---|---|
| Direct LLM API calls | No structured enforcement of citation rules |
| LangChain RAG | Could index Acts but no built-in compliance markers |
| **LARGESTACK legaltech_app template** | **Indian-first by default**: Act citations enforced via guardrails, eSign integration, MCA company lookup, DPDP markers |

## Specific LARGESTACK features used

| Feature | What it solved |
|---|---|
| `legaltech_app` cookiecutter template | Day 1 setup with Indian Acts compliance markers |
| `MCAToolkit.mca_lookup_company` | Look up CIN before drafting MoUs (avoids draft errors) |
| `eSignToolkit.esign_initiate` | Aadhaar-based eSign via eMudhra/NSDL |
| `eSignToolkit.esign_check_status` | Track signature workflow |
| Hallucination guardrail | Critical for legal accuracy — flags non-existent Act sections |
| `compliance: [Indian_Contract_Act_1872, Indian_Stamp_Act_1899, IT_Act_2000]` | Embedded in agent.yaml — auditable |
| Indian PII scanning | Pre-publication scan catches hardcoded PANs / Aadhaars in templates |

## Architecture

```text
User selects template → LARGESTACK agent fills:
  ├── Cite specific Acts/Sections (forced via system prompt)
  ├── Use Indian English (cheque, judgement, wilful)
  ├── Flag stamp duty obligations per state
  ├── Lookup MCA for any company name (CIN auto-attached)
  └── Initiate eSign workflow if user opts in (eMudhra/NSDL)

All output runs through:
  ├── Hallucination guardrail (catches phantom Section 999.99)
  ├── PII redaction (catches accidental Aadhaar in template metadata)
  └── DPDP audit log (every draft = one chain entry)
```

## Outcomes

- **96 templates ship with proper Indian Act citations** — every
  template tagged with the controlling Acts in YAML
- **eSign in 1 click** — Aadhaar OTP-based signing via eMudhra
  sandbox; production NSDL ready
- **Stamp duty aware** — drafts include disclaimer with state-specific
  duty rates (built from a small reference table loaded at agent
  init)
- **Investor-ready compliance posture** — DPDP/Stamp Act/IT Act
  markers in YAML are demo-able to compliance officers

## Bottom line

Building this on LangChain would have required custom code for:
- Indian Act lookup table
- Indian English enforcement (custom prompt scaffolding)
- eSign aggregator integration (eMudhra has no Python SDK)
- Stamp duty table by state
- DPDP-compliant PII handling on user-supplied data

LARGESTACK shipped all of the above in the `legaltech_app` template plus
toolkits. Integration time: **2 weeks**. Estimated LangChain-from-scratch
time: **3-4 months**.

---

**Stack:** FastAPI backend + Next.js frontend + LARGESTACK toolkits + 96
templates indexed in pgvector + eMudhra eSign + Razorpay (₹X per
template)

**Sole production blocker:** Signzy eSign/eStamp business approval
(operational process, not technical)
