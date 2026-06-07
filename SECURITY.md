# Security Policy

## Reporting

Email: security@largestack.ai (PGP key on website)

Do **not** open public GitHub issues for security vulnerabilities.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.1.x   | ✅        |
| < 1.1   | ❌        |

## Disclosure Timeline

- Day 0: Report received → acknowledged within 48h
- Day 7: Initial assessment
- Day 30: Fix released
- Day 90: Public disclosure

## Security Features

- AES-256-GCM encryption (vault)
- HMAC-SHA256 hash chain (audit log)
- mTLS support
- RBAC with role-based permissions
- 15 guardrail layers (OWASP ASI coverage)
- SBOM via CycloneDX 1.6 + SPDX 3.0
