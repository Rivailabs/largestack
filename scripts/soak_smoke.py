"""Offline-friendly soak smoke check for Largestack AI deployments."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def _get(url: str, api_key: str | None = None, timeout: float = 10.0) -> tuple[int, str]:
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 - operator-supplied local URL
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Largestack AI deployment soak smoke check")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--api-key", default="test-key")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args(argv)

    failures: list[dict] = []
    for i in range(1, args.iterations + 1):
        health_code, health_body = _get(f"{args.base_url}/health")
        metrics_code, metrics_body = _get(f"{args.base_url}/api/metrics", args.api_key)
        row = {
            "iteration": i,
            "health": health_code,
            "metrics": metrics_code,
        }
        print(json.dumps(row, sort_keys=True))
        if health_code >= 400:
            failures.append({"iteration": i, "endpoint": "health", "status": health_code, "body": health_body[:200]})
        if metrics_code >= 400:
            failures.append({"iteration": i, "endpoint": "metrics", "status": metrics_code, "body": metrics_body[:200]})
        if i != args.iterations:
            time.sleep(args.sleep)

    if failures:
        print(json.dumps({"failures": failures}, indent=2), file=sys.stderr)
        return 1
    print("SOAK_SMOKE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

