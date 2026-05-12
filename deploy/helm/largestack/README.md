# LARGESTACK Helm Chart

Production Kubernetes deployment of Largestack AI.

## TL;DR
```bash
helm dependency build
kubectl create namespace largestack
kubectl create secret generic largestack-secrets \
    --namespace largestack \
    --from-literal=OPENAI_API_KEY=sk-...

helm install my-largestack . --namespace largestack
```

Upgrade:

```bash
helm upgrade my-largestack . --namespace largestack
```

Uninstall:

```bash
helm uninstall my-largestack --namespace largestack
```

## What's included

| Resource | Purpose |
|---|---|
| Deployment | LARGESTACK app with liveness/readiness probes, non-root, hardened security context |
| Service | ClusterIP exposing port 8000 |
| HorizontalPodAutoscaler | Scale 2 → 10 pods on CPU/memory |
| ConfigMap | mounts `agent.yaml` |
| Secret reference | provider API keys via external secret |
| Ingress | optional, defaults disabled |
| Bitnami subcharts | optional Redis + Postgres |

## Values

See `values.yaml` for the complete option set. Key knobs:

```yaml
image:
  repository: rivailabs/largestack
  tag: "0.14.2"

resources:
  requests: { cpu: 500m, memory: 512Mi }
  limits:   { cpu: 2000m, memory: 2Gi }

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10

otel:
  enabled: true
  endpoint: http://otel-collector.observability.svc.cluster.local:4317
```

## Production hardening

1. **Use external Postgres + Redis** (set `redis.enabled=false`, `postgresql.enabled=false`)
2. **Inject provider keys via a managed secret** (External Secrets Operator + Vault/AWS SM)
3. **Pin image SHA**, not tag (avoids supply-chain surprises)
4. **Enable PodSecurityPolicy / OPA / Kyverno** for cluster-wide enforcement
5. **Set up NetworkPolicy** to lock down pod-to-pod traffic
6. **DPDP data residency**: deploy in AWS Mumbai or Azure India South for Indian fintech

## Ship as OCI artifact (Helm 3.8+)

```bash
helm package .
helm push largestack-0.14.3.tgz oci://ghcr.io/rivailabs
```
