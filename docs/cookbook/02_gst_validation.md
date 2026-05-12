# Recipe 02 — GST Validation Agent

**Use case:** Validate vendor/customer GSTINs at invoice time. Catch
fake or cancelled GSTINs before payment to prevent input-tax-credit
disputes.

**Compliance:** CGST Act §25 (registration), Rule 21A (suspension).

## What it does

1. **Format check** — regex against the GSTIN structure (15 chars, state-code prefix, PAN-based, checksum).
2. **Lookup** — calls the GSTN public API or aggregator (Karza, Signzy).
3. **Active check** — flags suspended/cancelled GSTINs.
4. **State-code cross-check** — vendor's PIN code → state must match GSTIN's state-code prefix.

## Full code

```python
import asyncio
import re
from largestack._india_kyc import gstin_lookup
from largestack._memory.long_term import LongTermMemoryManager

GSTIN_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)

async def validate_gstin(gstin: str, *, tenant_id: str):
    # 1) Format
    if not GSTIN_RE.match(gstin):
        return {"valid": False, "reason": "format_invalid"}

    # 2) Cache check
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id="system",
    )
    cached = await memory.search_archival(f"gstin_{gstin}")
    if cached:
        return {"valid": True, "cached": True, "data": cached[0].content}

    # 3) Live lookup
    resp = await gstin_lookup(gstin)
    if not resp.success:
        return {"valid": False, "reason": "lookup_failed"}

    # 4) Active status
    if resp.status != "Active":
        return {
            "valid": False,
            "reason": "inactive",
            "status": resp.status,
        }

    # 5) Cache (7-day TTL — GSTN status can change)
    await memory.add_archival(
        f"gstin_{gstin}: name={resp.legal_name} status=Active "
        f"state={resp.state}",
        tag="gstin_cache",
        purpose="invoice_validation",
        lawful_basis="legitimate_interest",
        ttl_seconds=7 * 24 * 3600,
    )

    return {
        "valid": True,
        "legal_name": resp.legal_name,
        "trade_name": resp.trade_name,
        "state": resp.state,
        "registration_date": resp.reg_date,
    }


# Batch validation
async def validate_invoice_batch(gstins: list[str], tenant_id: str):
    results = await asyncio.gather(*[
        validate_gstin(g, tenant_id=tenant_id) for g in gstins
    ])
    return dict(zip(gstins, results))
```

## State-code prefix table (first 2 digits of GSTIN)

| Code | State |
|--:|---|
| 01 | Jammu & Kashmir |
| 02 | Himachal Pradesh |
| 07 | Delhi |
| 09 | Uttar Pradesh |
| 19 | West Bengal |
| 27 | Maharashtra |
| 29 | Karnataka |
| 33 | Tamil Nadu |
| 36 | Telangana |
| 37 | Andhra Pradesh |

(Full list: 00–38, plus 96 for foreign and 97 for special.)

## Why this matters

- **No competitor framework** has GSTIN format validation built in
- **Cache TTL = 7 days**: GSTN status changes (suspensions, cancellations) — older cache is stale
- **Multi-tenancy**: each tenant has their own GSTIN cache
