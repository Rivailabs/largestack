#!/usr/bin/env python3
"""Optional external vector-store E2E smoke.

Runs only when QDRANT_URL or LARGESTACK_QDRANT_URL is provided. This keeps the
normal test suite deterministic while giving release engineers a real-service
check for Docker/Qdrant or managed Qdrant environments.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def main() -> int:
    url = os.environ.get("QDRANT_URL") or os.environ.get("LARGESTACK_QDRANT_URL")
    if not url:
        print("SKIP: set QDRANT_URL or LARGESTACK_QDRANT_URL to run external vector DB E2E")
        return 0

    try:
        from largestack._vectorstores import QdrantStore
    except Exception as exc:  # pragma: no cover - optional dependency path
        print(f"FAIL: QdrantStore import failed: {exc}", file=sys.stderr)
        return 2

    store = QdrantStore(url=url, collection="largestack_release_gate", dim=3, create_collection=True)
    await store.upsert([
        {"id": 1, "vector": [0.1, 0.2, 0.3], "metadata": {"text": "hello"}},
        {"id": 2, "vector": [0.3, 0.2, 0.1], "metadata": {"text": "world"}},
    ])
    results = await store.query([0.1, 0.2, 0.3], top_k=1)
    assert results, "Qdrant returned no results"
    print("PASS: external vector DB E2E returned", results[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
