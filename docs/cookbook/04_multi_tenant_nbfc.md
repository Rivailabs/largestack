# Recipe 04 — Multi-tenant NBFC Setup

**Use case:** You're hosting AI agents for multiple NBFCs (Sri
Rajeshwari Gold Loan, ABC Microfinance, XYZ Vehicle Finance). Each
tenant's data must be **isolated** at every layer — memory, audit
log, vector store, LLM cache.

**Compliance:** RBI Master Direction NBFC-D §6 (data segregation).

## The contract

Every LARGESTACK object that touches data takes a `tenant_id` parameter.
Cross-tenant queries are **rejected at the storage layer**, not just
filtered at query time. This is what RBI auditors verify.

## Setup

```python
import asyncio
from largestack._memory.long_term import (
    LongTermMemoryManager, SQLiteLongTermStore,
)
from largestack._compliance import AuditLogger
from largestack._tenancy import TenantConfig

# Single shared SQLite store — but tenant_id partitions every row
shared_store = SQLiteLongTermStore("/data/largestack_memory.db")

async def get_agent_for_tenant(tenant_id: str, user_id: str):
    """Build a tenant-scoped agent."""
    memory = LongTermMemoryManager(
        store=shared_store,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    audit = AuditLogger(tenant_id=tenant_id)
    return memory, audit


# Tenant A — Sri Rajeshwari
mem_a, audit_a = await get_agent_for_tenant(
    tenant_id="sri_rajeshwari", user_id="customer_42",
)
await mem_a.add_archival(
    "Customer prefers Kannada chat",
    purpose="personalization", lawful_basis="consent",
)

# Tenant B — ABC Microfinance
mem_b, audit_b = await get_agent_for_tenant(
    tenant_id="abc_microfinance", user_id="customer_42",
)
# Same user_id, different tenant — completely separate data

# Cross-tenant query attempt → returns nothing
results = await mem_a.list_all()
# Will only see sri_rajeshwari's data, not abc_microfinance
```

## What's enforced

| Layer | Tenant isolation |
|---|---|
| `LongTermMemoryManager` | Constructor rejects empty `tenant_id`; all reads filter by tenant |
| `forget()` | Refuses to delete entries belonging to a different tenant |
| `forget_user()` | Only deletes entries matching `(tenant_id, user_id)` |
| `SQLiteLongTermStore` | Every row indexed on `tenant_id`; SQL always parameterizes it |
| `AuditLogger` | Hash-chains are per-tenant (you can prove non-tampering for one tenant without the other's data) |
| Vector stores | Use namespace/collection-per-tenant (Qdrant collections, Pinecone namespaces) |

## Tenant onboarding script

```python
async def onboard_tenant(tenant_id: str, plan: str = "standard"):
    """Provision a new tenant. Idempotent."""
    config = TenantConfig(
        tenant_id=tenant_id,
        plan=plan,
        compliance_markers=[
            "DPDP_Act_2023",
            "RBI_PA_PG_2024",
            "PMLA_2002",
        ],
        data_retention_days=8 * 365,  # RBI 8-year retention
    )
    await config.save()
    print(f"tenant {tenant_id} provisioned")


# Onboard
asyncio.run(onboard_tenant("new_nbfc", plan="enterprise"))
```

## Verifying isolation (run this at audit time)

```python
async def audit_tenant_isolation(tenant_a: str, tenant_b: str):
    """Verify no cross-tenant leakage. Run during compliance reviews."""
    mem_a = LongTermMemoryManager(
        store=shared_store, tenant_id=tenant_a, user_id="audit_probe",
    )
    # Ask for tenant B's known data — must return empty
    leaked = await mem_a.search_archival(f"tenant_{tenant_b}_data")
    assert len(leaked) == 0, f"LEAK: {tenant_a} can see {tenant_b}!"
    print("isolation verified ✓")
```

## Why this matters

- **RBI audits ask "can tenant A's agent see tenant B's data?"** — with LARGESTACK, the answer is "no, by construction"
- **DPDP §11**: data principal can request erasure for one tenant without affecting others
- **Single shared infra**: 100 NBFCs on one Postgres + Qdrant — no per-tenant DB sprawl
