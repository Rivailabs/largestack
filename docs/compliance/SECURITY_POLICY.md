# Largestack AI — Security Policy

## Encryption Standards
- **At rest**: AES-256-GCM with key rotation (PBKDF2 derivation)
- **In transit**: TLS 1.3 minimum, mTLS for inter-agent communication
- **Secrets**: Multi-backend vault (env/HashiCorp/AWS SM/encrypted file)
- **Passwords**: PBKDF2-HMAC-SHA256 with random 16-byte salt

## Access Control
- **Authentication**: JWT with signature verification (pyjwt + JWKS)
- **Authorization**: RBAC with 4 built-in roles (viewer/developer/operator/admin)
- **Tenancy**: Isolated per-tenant with tier-based rate limits
- **Sessions**: TTL-based with revocation support

## Agent Security (OWASP Agentic Security Initiative)
- **ASI02**: Tool access control — per-agent allow/deny lists
- **ASI03**: Agent identity — scoped credentials, session TTL
- **ASI06**: Memory integrity — injection pattern detection, SHA-256 tamper detection
- **ASI07**: Inter-agent auth — HMAC-SHA256 signed messages, replay protection

## Data Protection
- **PII Detection**: Regex + Presidio + spaCy NER (3-layer)
- **PII Actions**: Block, redact, or warn (configurable)
- **Audit Trail**: Append-only with cryptographic hash chain (tamper-evident)
- **Data Retention**: Configurable per-table (default 30 days for traces)

## Network Security
- **URL/IP allowlists**: CIDR range support
- **Rate limiting**: Per-host with configurable window
- **HTTPS enforcement**: Configurable `https_only` policy
- **Code sandbox**: subprocess/Docker/E2B with network isolation

## Vulnerability Disclosure
Report security issues to: security@rivailabs.com
Response commitment: 48 hours acknowledgment, 7-day assessment

## SBOM
Generated in CycloneDX 1.5 and SPDX 2.3 formats.
Run: `python -c "from largestack._security.sbom import SBOMGenerator; SBOMGenerator().generate('cyclonedx', 'sbom.json')"`
