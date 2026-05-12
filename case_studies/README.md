# LARGESTACK Case Studies

Real Indian fintech/legaltech deployments built on LARGESTACK.

| Project | Sector | Key LARGESTACK features used |
|---|---|---|
| [Sri Rajeshwari Gold & Silver](sri_rajeshwari_nbfc.md) | NBFC / Gold loans | KYCToolkit, UPIToolkit, audit chain, multi-tenancy |
| [LegalDocs.in](legaldocs_in.md) | LegalTech | legaltech_app template, MCAToolkit, eSignToolkit |

## Pattern

Every Indian fintech/legaltech use case shares three structural needs:

1. **Indian aggregator integrations** (Razorpay / Signzy / IDfy /
   eMudhra / Probe42 / MasterGST) — these are commodity to LARGESTACK
   but custom-build elsewhere
2. **DPDP/RBI compliance posture** — markers, audit chain,
   PII redaction baked in
3. **Indic-aware text handling** (v0.11+) — Hindi, Tamil, Telugu,
   Bengali tokenization + PII detection

The competitive math: building these three layers from scratch on
LangChain or LlamaIndex takes **3-6 months**. Adopting LARGESTACK
collapses it to **2-8 weeks**.
