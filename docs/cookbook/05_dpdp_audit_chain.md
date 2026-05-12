# Recipe 05 — DPDP Audit Chain

**Use case:** Prove to a DPDP auditor (or DPO) that a specific
customer's consent was honoured for every data operation, with
**tamper-evident logs**.

**DPDP:** §11 (data principal rights — access, correction, erasure,
nomination), §28 (data fiduciary obligations).

## What hash-chained means

Every audit entry has a `prev_hash` field that is the SHA-256 of the
previous entry. Tampering with any entry invalidates all subsequent
hashes — auditors can verify the whole chain in O(n).

## Full code

```python
import asyncio
from largestack._compliance import AuditLogger, verify_audit_chain
from datetime import datetime, timezone

async def consent_event_log(tenant_id: str, user_id: str):
    audit = AuditLogger(tenant_id=tenant_id)

    # Customer grants consent for KYC
    await audit.log({
        "event": "consent_granted",
        "user_id": user_id,
        "purpose": "KYC_for_loan_product",
        "lawful_basis": "consent",
        "expires_at": "2027-05-01T00:00:00Z",
    })

    # Three months later, customer requests data export
    await audit.log({
        "event": "data_export_request",
        "user_id": user_id,
        "section": "DPDP_§11(b)",  # right to access
        "fulfilled_at": datetime.now(tz=timezone.utc).isoformat(),
    })

    # Customer requests erasure
    await audit.log({
        "event": "erasure_requested",
        "user_id": user_id,
        "section": "DPDP_§11(d)",
        "scope": "all_personal_data",
    })

    # Verify the chain (every entry's prev_hash matches)
    ok, broken_at = await verify_audit_chain(tenant_id=tenant_id)
    if not ok:
        raise RuntimeError(f"audit chain broken at index {broken_at}")
    print(f"audit chain verified ✓")


asyncio.run(consent_event_log(
    tenant_id="my_nbfc", user_id="customer_42",
))
```

## Audit log schema

Every entry has these system fields plus your event-specific payload:

```json
{
  "index": 42,
  "timestamp": 1714752000.123,
  "tenant_id": "my_nbfc",
  "prev_hash": "a3b1c9...",
  "this_hash": "f7d2e1...",
  "event": "consent_granted",
  ...your custom fields...
}
```

## Common DPDP events to log

| Event | When | DPDP section |
|---|---|---|
| `consent_granted` | User gives explicit consent | §6 |
| `consent_withdrawn` | User revokes consent | §6(4) |
| `data_export_request` | User requests their data | §11(b) |
| `correction_request` | User requests data correction | §11(c) |
| `erasure_requested` | User requests deletion | §11(d) |
| `breach_detected` | Security incident | §8 |
| `breach_notified` | DPB notification sent | §8 |
| `nomination_set` | User nominates a representative | §11(e) |

## Exporting for auditors

```python
async def export_for_audit(tenant_id: str, user_id: str):
    """Export all events for a user as a signed PDF."""
    audit = AuditLogger(tenant_id=tenant_id)
    events = await audit.query(filters={"user_id": user_id})

    # Verify before export — never ship a tampered chain
    ok, _ = await verify_audit_chain(tenant_id=tenant_id)
    assert ok, "chain broken; cannot export"

    # Format as PDF (uses LARGESTACK audit-export CLI)
    return await audit.export(
        format="pdf",
        path=f"./audit_{user_id}_{tenant_id}.pdf",
    )
```

## Why this matters

- **DPB inspections**: India's Data Protection Board can demand consent + processing records on 24-hour notice
- **Litigation**: hash-chained logs are admissible as evidence (CrPC §65B equivalent)
- **Auditor-friendly**: a single SHA verification proves no tampering; auditors don't need to read every line
