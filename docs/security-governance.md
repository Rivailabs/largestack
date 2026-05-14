# Security and Governance

Largestack is designed around controlled AI execution. The goal is not only to call LLMs, but to prevent unsafe AI behavior in real applications.

---

## Security surfaces

| Surface | Control |
|---|---|
| Prompt input | Injection and sensitive-content checks |
| Model provider | Provider policy and routing controls |
| Tool calls | Permissions, approval, sandbox, timeout, retry |
| RAG | Citation, no-answer, tenant filtering patterns |
| Memory | Isolation and controlled persistence |
| Output | PII and policy checks |
| Enterprise | RBAC, audit, tenant scoping, session/SSO foundations |
| Deployment | Docker, Helm, environment-variable based secrets |

---

## Secret safety

Never commit:

- `.env`,
- API keys,
- service account JSON,
- database passwords,
- cloud tokens,
- SSH private keys.

Before every release:

```bash
gitleaks detect --source . --no-git
```

If a key was ever pasted into chat or committed accidentally, rotate it immediately.

---

## Security validation commands

```bash
python -m pytest tests/security -q --tb=short -ra
bandit -r largestack -x tests -ll
pip-audit
gitleaks detect --source . --no-git
```

---

## Enterprise honesty

Largestack has strong enterprise foundations, but regulated enterprise claims require external proof.

Do not claim BFSI-certified or SOC2-ready until:

- external VAPT is complete,
- tenant isolation is independently tested,
- audit retention policy is documented,
- incident process exists,
- compliance evidence is reviewed,
- K8s/deployment hardening is complete.
