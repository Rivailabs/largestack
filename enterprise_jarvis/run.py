#!/usr/bin/env python3
"""Enterprise Jarvis CLI demo.

Usage:
    python run.py --demo
    python run.py --once "message" [--role admin|agent|viewer] [--tenant acme] [--user alice]

Requires a provider key, e.g.:  export LARGESTACK_DEEPSEEK_API_KEY="sk-..."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ejarvis import store  # noqa: E402
from ejarvis.agent import EnterpriseJarvis  # noqa: E402
from ejarvis.config import MODEL, has_api_key  # noqa: E402
from ejarvis.context import Principal  # noqa: E402

# (principal, message) — exercises RBAC, multi-tenant, RAG, approvals, audit.
DEMO = [
    (
        Principal("alice", "admin", "acme"),
        "How many annual leave days do I get? Check the knowledge base.",
    ),
    (Principal("alice", "admin", "acme"), "Remember that my manager is Bob."),
    (
        Principal("dave", "viewer", "acme"),
        "Raise a support ticket: my VPN is broken.",
    ),  # viewer → denied
    (
        Principal("carol", "agent", "acme"),
        "Raise a support ticket: VPN is broken for the sales team.",
    ),
    (Principal("carol", "agent", "acme"), "Please delete all production logs now."),  # → approval
    (Principal("alice", "admin", "acme"), "Show me the recent audit log."),
]


async def _one(principal: Principal, message: str) -> None:
    jarvis = EnterpriseJarvis(principal)
    out = await jarvis.ask(message)
    print(f"\n\033[1m[{principal.user}/{principal.role}@{principal.tenant}]\033[0m {message}")
    print(f"\033[36m  → {out.reply}\033[0m")
    print(f"\033[90m  · cost ${out.cost:.6f} · trace {out.trace_id}\033[0m")


async def run_demo() -> None:
    print(f"=== Enterprise Jarvis demo (model: {MODEL}) ===")
    for principal, message in DEMO:
        await _one(principal, message)
    # Typed (Pydantic) output path.
    jarvis = EnterpriseJarvis(Principal("alice", "admin", "acme"))
    t = await jarvis.triage("My laptop won't boot and I have a board demo in 1 hour.")
    print(
        f"\n\033[1m[typed triage]\033[0m category={t.category} priority={t.priority} "
        f"needs_approval={t.needs_approval}"
    )
    print(f"\033[90m  summary: {t.summary}\033[0m")
    # Show the persisted audit trail (proves tools ran + RBAC was enforced).
    print("\n=== audit trail (tenant acme) ===")
    for row in store.read_audit("acme", limit=12):
        print(f"  {row['at']}  {row['user']}/{row['role']}  {row['event']}  {row['detail']}")


async def run_once(message: str, principal: Principal) -> None:
    await _one(principal, message)


def main() -> int:
    ap = argparse.ArgumentParser(description="Enterprise Jarvis on Largestack")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--once", metavar="MSG")
    ap.add_argument("--role", default="admin", choices=["admin", "agent", "viewer"])
    ap.add_argument("--tenant", default="acme")
    ap.add_argument("--user", default="alice")
    args = ap.parse_args()

    if not has_api_key():
        print(f"No API key for model '{MODEL}'. Set LARGESTACK_DEEPSEEK_API_KEY.", file=sys.stderr)
        return 2

    if args.demo:
        asyncio.run(run_demo())
    elif args.once:
        asyncio.run(run_once(args.once, Principal(args.user, args.role, args.tenant)))
    else:
        print('Use --demo or --once "message".', file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
