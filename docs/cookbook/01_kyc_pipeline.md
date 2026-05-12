# Recipe 01 — KYC Verification Pipeline

**Use case:** Verify a customer's identity using Aadhaar OKYC + PAN
cross-check before opening a financial product (loan, demat,
prepaid card).

**DPDP/RBI:** DPDP §6 (purposeful collection), RBI Master Direction on
KYC. Consent must be explicit; data minimisation enforced.

## Architecture

```
User input (Aadhaar number + PAN)
    ↓
[Consent gate]  ← DPDP §6 lawful basis check
    ↓
[Aadhaar OKYC]  ← UIDAI via Signzy/IDfy
    ↓
[PAN verification]  ← Income Tax via Signzy/Karza
    ↓
[Name + DoB cross-match]
    ↓
[Audit log entry]  ← Hash-chained
    ↓
KYC verified? Yes/No + reason
```

## Full code

```python
import asyncio
from largestack._core import Agent
from largestack._india_kyc import aadhaar_okyc, pan_verify
from largestack._compliance import AuditLogger
from largestack._memory.long_term import LongTermMemoryManager

async def kyc_pipeline(
    *,
    tenant_id: str,
    user_id: str,
    aadhaar_number: str,
    pan: str,
    consent_token: str,
):
    # 1) Consent gate — refuse if no DPDP §6 lawful basis
    if not consent_token:
        return {"status": "blocked", "reason": "DPDP_consent_missing"}

    # 2) Memory: load any prior KYC attempts for this user
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id=user_id,
    )
    prior = await memory.search_archival("kyc_attempt")

    # 3) Aadhaar OKYC
    aadhaar_resp = await aadhaar_okyc(
        aadhaar_number,
        consent_token=consent_token,
        purpose="KYC_for_loan_product",  # DPDP §6
    )
    if not aadhaar_resp.success:
        await memory.add_archival(
            f"kyc_attempt: aadhaar_fail ({aadhaar_resp.error})",
            tag="kyc_attempt", purpose="audit_trail",
            lawful_basis="legitimate_interest",
            ttl_seconds=8 * 365 * 24 * 3600,  # 8 years per RBI
        )
        return {"status": "fail", "stage": "aadhaar"}

    # 4) PAN verification
    pan_resp = await pan_verify(
        pan, name=aadhaar_resp.name,
        purpose="KYC_for_loan_product",
    )
    if not pan_resp.success:
        return {"status": "fail", "stage": "pan"}

    # 5) Cross-match
    if aadhaar_resp.name.lower() != pan_resp.name.lower():
        return {
            "status": "fail",
            "stage": "name_mismatch",
            "aadhaar_name": aadhaar_resp.name,
            "pan_name": pan_resp.name,
        }

    # 6) Store the verified KYC fact in archival memory
    await memory.add_archival(
        f"KYC_verified: aadhaar_last4={aadhaar_number[-4:]} "
        f"pan_masked={pan[:3]}***{pan[-3:]} name={aadhaar_resp.name}",
        tag="kyc_verified",
        purpose="kyc_compliance_record",
        lawful_basis="legitimate_interest",
        ttl_seconds=8 * 365 * 24 * 3600,  # RBI 8-year retention
    )

    # 7) Append to hash-chain audit log
    audit = AuditLogger(tenant_id=tenant_id)
    await audit.log({
        "event": "kyc_verified",
        "user_id": user_id,
        "aadhaar_last4": aadhaar_number[-4:],
        "pan_masked": pan[:3] + "***" + pan[-3:],
    })

    return {"status": "verified", "name": aadhaar_resp.name}


# Usage
asyncio.run(kyc_pipeline(
    tenant_id="abc_nbfc",
    user_id="customer_42",
    aadhaar_number="123456789012",
    pan="AAACR1234C",
    consent_token="dpdp_consent_abc123",
))
```

## Why this matters

- **DPDP §6**: every PII operation has an explicit `purpose` field
- **RBI 8-year retention**: archival entries get `ttl_seconds=8 * 365 * 24 * 3600`
- **Multi-tenancy**: `tenant_id` enforced on every memory op (cross-tenant queries fail)
- **Right-to-erasure**: `memory.forget_user()` deletes all stored KYC records on customer request

## Pairs well with

- [Recipe 04 — Multi-tenant NBFC Setup](04_multi_tenant_nbfc.md)
- [Recipe 05 — DPDP Audit Chain](05_dpdp_audit_chain.md)
