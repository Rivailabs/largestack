# Largestack AI — Helm Chart

Legacy compatibility path. The canonical chart is `deploy/helm/largestack`.
Keep this directory only for users who still reference the old path; new docs,
tests, and release validation use `deploy/helm/largestack`.

Deploy Largestack AI's dashboard + serve API on Kubernetes.

## Install

```bash
helm install my-largestack deploy/helm/largestack/ \
  --namespace largestack --create-namespace \
  --set secrets.dashboardKey="$(openssl rand -hex 32)" \
  --set secrets.openaiKey="$YOUR_OPENAI_KEY"
```

The chart **refuses to install with an empty `dashboardKey`** — see
`templates/secret.yaml`.

## Production setup (multi-replica)

The default chart deploys a single replica. To scale horizontally:

```yaml
# values-prod.yaml
replicaCount: 3
env:
  LARGESTACK_RATE_LIMIT_BACKEND: redis
secrets:
  redisUrl: redis://redis-master.redis.svc.cluster.local:6379/0
persistence:
  enabled: true
  size: 10Gi
  storageClassName: standard
```

```bash
helm install largestack-prod deploy/helm/largestack/ \
  -f values-prod.yaml \
  --set secrets.dashboardKey="$(openssl rand -hex 32)"
```

> **Note:** for true multi-replica state isolation, configure Postgres
> via env vars (`LARGESTACK_POSTGRES_URL`) — the bundled SQLite databases
> are per-pod by default. See `docs/known-limitations.md`.

## Verify

```bash
kubectl rollout status deploy/my-largestack
kubectl port-forward svc/my-largestack 8787:8787
curl -H "X-API-Key: $KEY" http://localhost:8787/api/metrics
```

## Upgrade

```bash
helm upgrade my-largestack deploy/helm/largestack/ \
  --reuse-values --set image.tag=0.4.1
```

## Uninstall

```bash
helm uninstall my-largestack -n largestack
# PVC is NOT deleted automatically — protect against accidents:
kubectl delete pvc -l app.kubernetes.io/instance=my-largestack -n largestack
```

## Values reference

See `values.yaml` for the full annotated list. Required keys:
`secrets.dashboardKey`. Recommended keys for prod:
`replicaCount`, `env.LARGESTACK_RATE_LIMIT_BACKEND`, `secrets.redisUrl`,
`persistence.enabled`, `ingress.enabled` + `ingress.hosts`.
