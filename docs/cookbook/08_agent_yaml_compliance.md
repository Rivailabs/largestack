# Recipe 08 — agent.yaml Compliance Markers

**Use case:** Embed compliance metadata directly in your agent
definition. Auditors can read `agent.yaml` and immediately see which
acts/sections the agent is built against.

## Full agent.yaml example

```yaml
name: nbfc-loan-origination-agent
version: 1.0.0
description: |
  Loan origination agent for NBFCs. Performs KYC, eligibility
  checks, and document signing. India-only deployment.
model: openai/gpt-4o-mini
tenant_id: ${TENANT_ID}

# Per-agent compliance markers — visible in LARGESTACK Studio
compliance:
  - name: DPDP_Act_2023
    section: Section 6
    notes: explicit purpose-bound consent for KYC PII
  - name: DPDP_Act_2023
    section: Section 8
    notes: breach notification path configured
  - name: RBI_PA_PG_2024
    section: Para 5.4
    notes: data localization — all PII stays in India
  - name: RBI_MD_NBFC_D
    section: Section 6
    notes: tenant-level data segregation enforced
  - name: PMLA_2002
    section: Rule 9
    notes: customer due diligence + STR filing supported
  - name: IT_Act_2000
    section: Section 3A
    notes: Aadhaar eSign legally equivalent to wet signature

# Memory configuration (Letta-pattern)
memory:
  store: sqlite  # or postgres for production
  store_path: /data/largestack_memory.db
  core_block_chars: 1500
  recall_top_k: 5
  default_ttl_days: 30  # for recall tier
  archival_ttl_days: 2920  # 8 years (RBI retention)

# India-specific tools
tools:
  - aadhaar_okyc
  - pan_verify
  - gstin_lookup
  - mca_lookup
  - esign_signzy
  - cibil_score
  - ckyc_search

# Audit + observability
audit:
  enabled: true
  hash_chain: true
  retention_years: 8

# Data residency
data_residency:
  region: india
  allowed_llm_providers:
    - aws_bedrock_mumbai
    - azure_india_central
    - openai_azure_india
  blocked_llm_providers:
    - deepseek  # China-hosted
    - moonshot  # China-hosted
```

## Why each marker matters

| Marker | What it tells the auditor |
|---|---|
| `DPDP_Act_2023 §6` | Every PII operation has an explicit purpose |
| `DPDP_Act_2023 §8` | Breach detection + 72-hour DPB notification configured |
| `RBI_PA_PG_2024 §5.4` | Payment data stays in India |
| `RBI_MD_NBFC_D §6` | Multi-tenant isolation verified |
| `PMLA_2002 Rule 9` | Customer due diligence happens before high-value txn |
| `IT_Act_2000 §3A` | eSign is treated as legally binding |

## Reading markers programmatically

```python
import yaml
from pathlib import Path

def get_compliance_markers(agent_yaml: Path) -> list[dict]:
    spec = yaml.safe_load(agent_yaml.read_text())
    return spec.get("compliance", [])

# In Studio export
from largestack._studio import StudioBuilder, ComplianceMarker
builder = StudioBuilder(title=spec["name"])
for c in get_compliance_markers(Path("agent.yaml")):
    builder.add_compliance(ComplianceMarker(
        name=c["name"], section=c.get("section", ""),
        notes=c.get("notes", ""),
    ))
```

## Auditor checklist (run before deployment)

```bash
largestack compliance-check agent.yaml --fail-on-missing
```

This validates:

- [ ] At least one DPDP marker present
- [ ] If financial-sector keywords present, RBI markers required
- [ ] `tenant_id` is parameterized (not hardcoded)
- [ ] `audit.enabled: true`
- [ ] `data_residency.region: india` (for India deployments)
- [ ] No blocked LLM providers in `allowed_llm_providers`

## Why this matters

- **One file = full compliance posture**: auditors read `agent.yaml`, not 50 source files
- **Diffable**: changes to compliance show up cleanly in PR reviews
- **LARGESTACK Studio renders these as colored tags** — visual proof for non-technical reviewers
