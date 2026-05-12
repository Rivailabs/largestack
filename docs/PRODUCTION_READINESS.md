# Production Readiness

This project should be classified from the latest validation evidence, not from old generated reports.

## Verified Areas

- Core agent SDK and typed agent API.
- Tool calling with schema generation, retries, timeout, and permissions tests.
- Multi-agent/team/orchestration flows.
- Memory, RAG, guardrails, security, RBAC, tenant scoping, and observability unit coverage.
- Smoke E2E and three production-style scenario scripts.
- Package metadata and build path when `python -m build` and `twine check` pass.

## Must Verify For Release

- Full pytest on Python 3.12 with timeout: `0 failed`, no timeout.
- Live DeepSeek tests when `LARGESTACK_DEEPSEEK_API_KEY` is set.
- Security scans: Bandit medium/high clean, pip-audit clean, no real secrets.
- Docker build and runtime health/auth probes.
- Fresh wheel install in a clean venv.

## Not Automatically Proven

- Public internet-scale reliability.
- BFSI/enterprise compliance approval.
- Customer-specific data residency.
- Cloud-managed database, KMS, SSO, SIEM, and incident response integration.

## Classification Rules

- Any failed required gate: Strong POC or lower.
- All local gates pass but no live provider validation: Private beta.
- All local gates and live DeepSeek pass, Docker runtime passes: Release candidate or controlled pilot depending on security review.
- Public production-ready requires external CI, signed artifacts, monitored deployments, and operational runbooks.
