# Deployment Guide

Largestack supports local development, Docker, Compose, and Helm-based deployment foundations.

---

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
python -m pytest tests -q --tb=short -ra
```

---

## Docker

```bash
docker build -t largestack:test .
docker run --rm -d --name largestack-test -p 8787:8787 largestack:test
curl http://127.0.0.1:8787/health
docker rm -f largestack-test
```

If Docker refuses to stop/remove a container with permission denied, treat it as a host/daemon issue, not automatically a code failure.

---

## Compose

Use the provided Compose files for local stack testing:

```bash
docker compose up --build
```

Check project-specific variables in `.env.example` and `deploy/.env.example`.

---

## Helm

Template/lint validation:

```bash
helm lint deploy/helm/largestack
helm template largestack deploy/helm/largestack > /tmp/largestack-rendered.yaml
```

Do not claim full Kubernetes production readiness until installed and tested on a real cluster with:

- liveness/readiness probes,
- autoscaling behavior,
- rolling upgrades,
- secrets handling,
- backup/restore,
- logs/metrics/traces.

---

## Production readiness ladder

| Stage | Requirement |
|---|---|
| Local demo | Full pytest + examples |
| Private pilot | Docker health + security scans + DeepSeek smoke |
| Controlled production | 24h soak + load test + alerting |
| Enterprise production | K8s install + VAPT + compliance evidence |
| BFSI/public SaaS | External audit, SLA, DR, tenant isolation, security certification |
