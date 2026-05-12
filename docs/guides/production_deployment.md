# Guide: Production Deployment

## Docker

```bash
docker build -t largestack-agent .
docker run -p 8787:8787 \
  -e LARGESTACK_OPENAI_API_KEY=<openai-api-key> \
  -e LARGESTACK_LICENSE_KEY=nxs_pro_... \
  -e LARGESTACK_ENV=production \
  largestack-agent
```

## Docker Compose (with PostgreSQL + Redis)

```bash
LARGESTACK_OPENAI_API_KEY=<openai-api-key> docker-compose up
```

This starts: largestack agent + postgres (pgvector) + redis (for kill switch).

## License for Production

Production is auto-detected when score ≥ 5 (container + cloud metadata + env variable).

```bash
# Set license
export LARGESTACK_LICENSE_KEY=nxs_pro_<sig>_<expiry>

# Verify
largestack license
```

## Health Checks

```bash
largestack doctor          # Check all dependencies
curl localhost:8787   # Dashboard health
```

## Monitoring

```bash
largestack dashboard       # Web UI at :8787
largestack cost            # CLI cost report
largestack trace           # CLI trace viewer
```

Prometheus metrics at `/api/metrics` (Prometheus exposition format).

## Kill Switch

```bash
# Emergency stop all agents
python -c "from largestack._guard.kill_switch import activate; activate('incident')"

# Resume
largestack resume
```
