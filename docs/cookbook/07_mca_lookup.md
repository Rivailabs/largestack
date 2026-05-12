# Recipe 07 — MCA Lookup Agent

**Use case:** Verify a counterparty company before extending credit or
signing a B2B contract. Fetch directors, paid-up capital, status from
MCA21 (Ministry of Corporate Affairs).

**Compliance:** Companies Act 2013, IBC §29A (related-party check).

## What an MCA lookup gives you

- **Company status** — Active / Strike-Off / Under Liquidation
- **Date of incorporation**
- **Authorized + paid-up capital**
- **Registered address**
- **Directors** (DIN numbers, names, roles)
- **Charges** (security interests over company assets)
- **Last AOC-4 / MGT-7 filing dates**

## Full code

```python
import asyncio
from largestack._india_kyc import mca_lookup, din_lookup
from largestack._memory.long_term import LongTermMemoryManager

async def vendor_due_diligence(
    *,
    tenant_id: str,
    cin: str,  # CIN: e.g. U72200KA2024PTC123456
):
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id="system",
    )

    # 1) Cache check (90-day TTL — MCA data changes slowly)
    cached = await memory.search_archival(f"mca_{cin}")
    if cached:
        return {"source": "cache", "data": cached[0].content}

    # 2) Live lookup
    co = await mca_lookup(cin)
    if not co.success:
        return {"status": "not_found"}

    # 3) Risk flags
    risks = []
    if co.status != "Active":
        risks.append(f"company_status_{co.status}")
    if co.last_filing_date and (
        (datetime.now() - co.last_filing_date).days > 365
    ):
        risks.append("last_annual_filing_overdue")
    if co.paid_up_capital < 100000:  # < ₹1 lakh
        risks.append("low_paid_up_capital")

    # 4) Director checks (look for IBC-disqualified directors)
    director_risks = []
    for director in co.directors:
        d = await din_lookup(director.din)
        if d.disqualified:
            director_risks.append(
                f"director_disqualified: {director.name} "
                f"(DIN {director.din})"
            )

    # 5) Cache result
    summary = (
        f"mca_{cin}: name={co.name} status={co.status} "
        f"paid_up={co.paid_up_capital} risks={risks}"
    )
    await memory.add_archival(
        summary, tag="mca_lookup",
        purpose="counterparty_due_diligence",
        lawful_basis="legitimate_interest",
        ttl_seconds=90 * 24 * 3600,
    )

    return {
        "status": "ok",
        "company": co.name,
        "incorporation_date": co.doi,
        "directors": [d.name for d in co.directors],
        "paid_up_capital": co.paid_up_capital,
        "risks": risks + director_risks,
    }
```

## CIN format reference

CIN (Corporate Identification Number) is 21 characters:

```
U 72200 KA 2024 PTC 123456
│ │     │  │    │   │
│ │     │  │    │   └─ Sequential number
│ │     │  │    └───── Company class:
│ │     │  │            PTC = Private Limited
│ │     │  │            PLC = Public Limited
│ │     │  │            FTC = Foreign company
│ │     │  └─────────── Year of incorporation
│ │     └────────────── State code
│ └──────────────────── Industry code (NIC 2008)
└────────────────────── Listing status: U=Unlisted, L=Listed
```

## Common risk signals

| Signal | Meaning |
|---|---|
| Status = "Strike Off" | Company de-registered; cannot legally transact |
| Status = "Under Liquidation" | NCLT proceedings underway; payments may be clawed back |
| `last_annual_filing_overdue` | MCA might strike them off; financials unverified |
| `director_disqualified` | At least one director under IBC §164 disqualification |
| `paid_up_capital < ₹1 lakh` | Likely a shell company |
| Multiple companies at same address | Possible front company cluster |

## Why this matters

- **No competitor framework** has MCA21 integration built in
- **Fraud prevention**: catching "Strike Off" status before signing saves crores
- **IBC compliance**: lending to disqualified directors triggers §29A bar
