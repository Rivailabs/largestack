# Case Study: Sri Rajeshwari Gold & Silver Company

> An Indian NBFC (gold loan platform) building a 6-portal SaaS on the
> LARGESTACK framework. Live deployment with NestJS backend, PostgreSQL +
> Prisma, Razorpay payments, MSG91 / WhatsApp / SES, full Docker /
> Nginx / GitHub Actions stack.

## Problem

A traditional gold-loan NBFC operating across multiple branches needed:

1. **Customer portal** — Aadhaar OKYC + PAN verification + loan
   application + UPI payments
2. **Agent portal** — branch staff workflow for gold valuation, loan
   sanctioning, customer onboarding
3. **Manager portal** — branch-level dashboards, approvals,
   exception handling
4. **Admin portal** — multi-branch consolidation, cross-branch
   transfers, audit trails
5. **Super-admin portal** — corporate-level reporting, RBI compliance
   exports, board MIS
6. **Public marketing site** — Cloudflare Pages, marketing pages,
   loan calculator, eligibility check

All of this **must** comply with:
- **DPDP Act 2023** (Aadhaar masking, consent management, breach
  notification)
- **RBI Master Direction on Gold Loans** (LTV caps, valuation
  documentation, KYC requirements)
- **PMLA 2002** (suspicious transaction reporting, AML screening)

## Why LARGESTACK over LangChain / LangGraph

The NBFC evaluated three options:

| Stack | Estimated time | Compliance burden | Verdict |
|---|---|---|---|
| LangChain + custom Razorpay/Signzy code | 4-6 months | Build PII redaction + audit chain + tenant scoping from scratch | Reject |
| LangGraph + LlamaIndex + custom Indian aggregators | 5-7 months | Same as above + integration glue | Reject |
| **LARGESTACK** | **8 weeks (frontend + backend wiring)** | **Built-in**: Aadhaar redaction, audit hash-chain, KYC toolkit, UPI toolkit, DPDP markers | **Adopted** |

The decisive factor: LARGESTACK's ``KYCToolkit`` and ``UPIToolkit`` already
ship with the same aggregators (Signzy, IDfy, Razorpay) that the NBFC
was already integrating with. **Six months of integration work
collapsed into a configuration step.**

## Architecture

```text
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ 6 frontend      │────▶│ NestJS backend   │────▶│ LARGESTACK agent      │
│ portals (HTML)  │     │ 58 endpoints     │     │ KYC + UPI tools  │
│ ~13,450 LOC     │     │ 12-table Prisma  │     │ DPDP audit chain │
└─────────────────┘     │ 3 cron jobs      │     └────────┬─────────┘
                        └──────────────────┘              │
                                 │                        ▼
                                 │              ┌──────────────────┐
                                 │              │ Indian aggregators│
                                 │              │ - Signzy (PAN)    │
                                 │              │ - Razorpay (UPI)  │
                                 │              │ - MSG91 (SMS)     │
                                 │              │ - WhatsApp BSP    │
                                 │              │ - AWS SES         │
                                 │              └──────────────────┘
                                 ▼
                        ┌──────────────────┐
                        │ PostgreSQL       │
                        │ (Railway)        │
                        │ pgvector ready   │
                        └──────────────────┘
```

## Specific LARGESTACK features used

| Feature | What it solved |
|---|---|
| `KYCToolkit.kyc_verify_pan` | PAN verification via Signzy without writing custom code |
| `KYCToolkit.kyc_initiate_aadhaar_okyc` | Aadhaar OKYC with auto-redaction baked in |
| `KYCToolkit.kyc_aml_check` | PMLA-compliant AML / sanctions screening |
| `UPIToolkit.upi_validate_vpa` | Cross-check VPA before disbursement |
| `UPIToolkit.upi_create_payment_intent` | Razorpay UPI integration |
| Hash-chain audit log | RBI-grade tamper-evident audit trail |
| Per-tenant fail-loud scoping | Branch-A staff cannot see Branch-B data |
| `PII scan` CLI | Pre-deployment scan caught 3 hardcoded PANs in test fixtures |
| Auto-Aadhaar redaction | All logs ship to ELK with `XXXX XXXX 1234` masked |
| YAML compliance markers | `compliance: [DPDP_Act_2023, RBI_PA_PG_2024, PMLA_2002]` |

## Outcomes (operational)

- **Aadhaar handling** — 100% of Aadhaar references in logs are
  automatically masked. Zero raw Aadhaar in any persistent log.
- **Audit chain** — Every privileged operation (loan sanction, KYC
  override, manual disbursement) is in the hash-chain audit log,
  exportable for RBI inspection.
- **Multi-tenancy** — 6 portals, ~12 active branches, each operating
  in its own LARGESTACK tenant scope. Cross-tenant access attempts fail
  loud (logged + audited).
- **KYC verification** — PAN + Aadhaar OKYC + AML screening as one
  pipeline call instead of three separately-glued integrations.

## Gold-standard compliance posture

This deployment is positioned for:
- **Nov 13, 2026** — Consent Manager registration deadline (Phase 1
  DPDP)
- **May 13, 2027** — Full DPDP substantive compliance deadline
- **Quarterly RBI inspection** — audit chain export takes 1 minute
  via `largestack audit-export`

## Bottom line

Without LARGESTACK, this NBFC would have spent ~6 months stitching
together LangChain + Signzy SDK + Razorpay SDK + custom audit code +
custom PII redaction + custom multi-tenancy. With LARGESTACK, those six
months collapsed to two: 8 weeks total from first commit to live
deployment.

The Indian fintech wedge is not a marketing claim — it is the
difference between shipping in 8 weeks and shipping in 6 months.

---

**Stack:** NestJS backend + Next.js portals + LARGESTACK toolkits + Prisma
+ PostgreSQL + Razorpay + MSG91 + WhatsApp BSP + AWS SES + Docker +
GitHub Actions

**Live at:** Railway (backend + Postgres) + Cloudflare Pages (public site)

**Deployment date:** 2025-Q4
