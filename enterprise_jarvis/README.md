# Enterprise Jarvis — an enterprise-style assistant on Largestack

A fuller, **enterprise-style** assistant built on the
[Largestack](https://pypi.org/project/largestack/) **typed decorator API** + DeepSeek.
It demonstrates the production surfaces an enterprise assistant needs — and every
one is exercised by a live demo and offline tests.

> **Enterprise-*style* reference/demo, not a certified production product.** It is
> honest about what's real (working RBAC, audit, approvals, RAG, guardrails) and
> what a real deployment still needs (SSO/IdP, a real vector DB, an approval UI,
> load testing, SOC2/VAPT).

## What it demonstrates
| Capability | How |
|---|---|
| **Typed agents & tools** | `Agent[Principal, str]` + `@agent.tool` with `RunContext[Principal]` (per AGENTS.md) |
| **RBAC** | `admin` / `agent` / `viewer` roles gate every tool; denials are audited |
| **Multi-tenant** | all memory / approvals / tickets / audit scoped per `tenant` |
| **Audit log** | append-only JSONL per tenant (`audit.jsonl`) — every tool call + run |
| **HITL approvals** | risky actions persist to an approval queue (`pending`, never executed) |
| **RAG + citations** | keyword retrieval over `knowledge/`, returns `[source]` citations |
| **Guardrails** | PII + injection guardrails on the typed agent |
| **Typed outputs** | `triage()` returns a validated `TicketTriage` Pydantic model |
| **Observability** | per-turn cost + trace id; full audit trail |
| **Safety** | bounded calculator (no `9**9**9` DoS), approval-gated risky actions |

## Quick start
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt           # largestack>=1.1.0
export LARGESTACK_DEEPSEEK_API_KEY="sk-..."

python run.py --demo                       # multi-role, multi-tenant live tour
python run.py --once "How many leave days do I get?" --role viewer --tenant acme
python -m pytest test_ejarvis.py -q        # offline tests (no key)
```

## Layout
```
enterprise_jarvis/
  run.py                  # CLI demo (--demo / --once, with --role/--tenant/--user)
  ejarvis/
    agent.py              # typed decorator agent + RBAC-gated, audited tools + triage
    context.py            # Principal (user, role, tenant) — the injected RunContext deps
    rbac.py               # role -> allowed actions
    store.py              # tenant-scoped memory / approvals / tickets / audit (JSONL)
    knowledge.py          # RAG retrieval with citations
    schemas.py            # TicketTriage (typed output)
    config.py
  knowledge/              # hr_leave_policy.md, it_support.md, security_policy.md
  test_ejarvis.py         # 11 offline tests
```

## Honest limitations (what a real production build still needs)
- Identity is a passed-in `Principal`, not real SSO/OIDC.
- RAG is keyword retrieval, not a vector database.
- The approval queue is a JSON file, not a reviewer UI + workflow engine.
- No load/concurrency testing, SOC2, or external VAPT.
