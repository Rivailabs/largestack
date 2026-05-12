# Largestack AI Control Plane Readiness

Largestack AI currently supports local and self-hosted operation through the CLI,
dashboard, Docker, Compose, Helm, traces, audit logs, and project scaffolds. A
managed control plane is future work and is not required for the current package
release.

## Future Managed Control Plane Shape

- Organizations and projects: team membership, project-level provider policies,
  and environment-scoped secrets.
- Run history: searchable runs, trace IDs, agent timeline, tool calls, RAG
  chunks, guardrail decisions, latency, and cost.
- Evaluation dashboard: datasets, scenarios, judge results, regression history,
  and release gates.
- Secrets: bring-your-own vault, key rotation metadata, and provider allowlists.
- Billing hooks: usage metering, tenant quotas, invoice export, and cost alerts.
- Deployment targets: local, Docker, Kubernetes, managed cloud jobs, and rollback
  records.

## Current Supported Surface

- `largestack dashboard` for local/self-hosted observability.
- `largestack trace` and `largestack cost` for terminal diagnostics.
- `largestack doctor` for project health and enterprise-readiness checks.
- `deploy/helm/largestack` as the canonical Kubernetes chart.

