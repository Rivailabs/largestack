# Largestack AI Soak Test

Use this procedure before a public or regulated deployment. It does not require
cloud provider keys unless your own agent config uses them.

## 24-Hour Procedure

1. Build the package and Docker image from a clean checkout.
2. Start the app with Docker or Helm using non-default dashboard/API keys.
3. Run `scripts/soak_smoke.py --iterations 288 --sleep 300` from a trusted host.
4. Watch health, `/api/metrics`, container restarts, memory, CPU, logs, and audit
   files.
5. Treat any non-2xx health response, auth bypass, process restart, or unbounded
   resource growth as a release blocker.

For a quick local rehearsal, run:

```bash
python scripts/soak_smoke.py --iterations 3 --sleep 1
```

