# LARGESTACK Cookbook — India-Fintech Recipes

Production-ready patterns for building agents on LARGESTACK for the Indian
fintech, legaltech, and regulated-industry market.

Each recipe is **self-contained**: copy the code, install LARGESTACK, run.

## Recipes

| # | Recipe | Use case | DPDP/RBI markers |
|--:|---|---|---|
| 01 | [KYC Verification Pipeline](01_kyc_pipeline.md) | Aadhaar OKYC + PAN cross-check | DPDP §6, RBI MD-KYC |
| 02 | [GST Validation Agent](02_gst_validation.md) | GSTIN format + GSTN lookup | CGST Act §25 |
| 03 | [Hindi Aadhaar Redaction](03_hindi_aadhaar_redaction.md) | Devanagari PII detection | DPDP §6, §7 |
| 04 | [Multi-tenant NBFC Setup](04_multi_tenant_nbfc.md) | Tenant isolation + per-tenant memory | RBI Master Direction NBFC-D |
| 05 | [DPDP Audit Chain](05_dpdp_audit_chain.md) | Hash-chain audit log for consent | DPDP §11 (data principal rights) |
| 06 | [eSign Workflow](06_esign_workflow.md) | Aadhaar-based document signing | IT Act 2000 §3A |
| 07 | [MCA Lookup Agent](07_mca_lookup.md) | CIN-based company verification | Companies Act 2013 |
| 08 | [agent.yaml Compliance Markers](08_agent_yaml_compliance.md) | Embedding compliance metadata | DPDP, RBI, PMLA |
| 09 | [Studio Export Walkthrough](09_studio_export.md) | Generating an HTML visualizer | n/a |
| 10 | [A2A Cross-Framework Interop](10_a2a_interop.md) | Exposing LARGESTACK agents over A2A | n/a |

## Prerequisites

```bash
pip install "largestack>=1.0.0"
```

For India-specific aggregators (Signzy / IDfy / Razorpay / DigiLocker),
configure API keys via `largestack secrets set` or a `.env` file.

For multi-modal document parsing, optionally install:

```bash
pip install llama-parse  # or llama-cloud-services
export LLAMA_CLOUD_API_KEY=llx-...
```

## Conventions used in these recipes

- All examples assume Python 3.11+
- All examples are async (use `asyncio.run(main())` or in a Jupyter notebook with `await`)
- All examples use the `tenant_id` + `user_id` multi-tenancy contract — never run a LARGESTACK agent without these in production
- DPDP fields (`purpose`, `lawful_basis`, `ttl_seconds`) are always set explicitly when storing PII
