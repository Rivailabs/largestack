# Security

## Secret Handling

Provider keys must be supplied through environment variables or a secret manager. Do not commit `.env`, shell transcripts, validation logs, or copied chat text containing keys. Rotate any key pasted into chat or logs.

## Required Release Scans

```bash
bandit -r largestack -x tests
bandit -r largestack -x tests --severity-level medium
pip-audit
gitleaks detect --source . --no-git
```

Release policy:

- No high or critical security issue is acceptable.
- No medium Bandit issue is acceptable unless documented with reason, containment, and owner.
- Low Bandit findings may remain only when they are false positives or accepted framework behavior.
- No real secret may be committed.

## Current Low-Finding Guidance

Common acceptable low findings include validated dynamic imports for optional integrations, validated SQL identifier formatting with parameterized values, and test-only fake secrets. Keep `# nosec` comments narrow and documented near the relevant code.

## Production Hardening Checklist

- Set `LARGESTACK_ENV=production`.
- Configure non-default dashboard/API auth.
- Use persistent tenant-scoped stores for RBAC, audit, sessions, and billing.
- Disable mock providers in production paths.
- Restrict CORS and network tool allowlists.
- Use TLS, container image scanning, and host-level log redaction.
