# Deployment

## Docker Build

```bash
docker build -t largestack:test .
docker build -f deploy/Dockerfile -t largestack:deploy-test .
```

## Runtime Probe

```bash
docker run --rm -d --name largestack-test -p 8787:8787 -e LARGESTACK_API_KEY=test-key -e LARGESTACK_DASHBOARD_KEY=test-key largestack:test
curl -i http://localhost:8787/health
curl -i -H 'X-API-Key: test-key' http://localhost:8787/api/metrics
curl -i -H 'X-API-Key: wrong-key' http://localhost:8787/api/metrics
docker rm -f largestack-test
```

Expected: health `200`, correct key `200`, wrong key `401` or `403`.

## Compose

```bash
docker compose config
docker compose up -d
docker compose ps
docker compose logs --tail=100
docker compose down
```

## Helm

Run `helm lint <chart-path>` when Helm is installed and chart files are present.

## Production Notes

Set real secrets through a secret manager, not baked images. Use non-default API keys/passwords, TLS at the edge, persistent databases for enterprise state, and centralized logs/metrics.
