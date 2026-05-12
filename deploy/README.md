# LARGESTACK Production Deployment

Hardened Docker Compose stack for production-like LARGESTACK deployments.

## Stack
| Service | Port | Purpose | Exposure |
|---|---:|---|---|
| `largestack` | 8000 | FastAPI agent server | host port |
| `redis` | 6379 | Sessions, checkpoints, rate limiting | internal only |
| `postgres` | 5432 | pgvector + audit log | internal only |
| `qdrant` | 6333 | Alternative vector store via `QdrantStore` | internal only |
| `prometheus` | 9090 | Metrics | host port |
| `grafana` | 3000 | Dashboards | host port |

## Quick start
```bash
cp deploy/.env.example deploy/.env
# Replace every change-me value and set at least one LARGESTACK_* provider key.
cd deploy
docker compose up -d --build
```

Test:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/metrics
```

## Production hardening checklist
- [ ] Put the app behind a TLS reverse proxy/load balancer.
- [ ] Replace all generated secrets in `.env`.
- [ ] Keep Redis/Postgres/Qdrant internal-only unless protected by private networking.
- [ ] Pin image digests for regulated deployments.
- [ ] Configure backups and restore drills for Postgres.
- [ ] Use external managed Postgres/Redis for multi-node production.
- [ ] Run the release gate in `docs/release-readiness.md`.
- [ ] Run security scanning and penetration testing before public exposure.

## Scaling
Single-host Compose is for production-like validation and private deployments, not large-scale SaaS. For real scale, deploy to Kubernetes using one canonical Helm chart under `deploy/helm/largestack`.
