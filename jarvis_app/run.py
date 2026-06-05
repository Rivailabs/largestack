#!/usr/bin/env python3
"""Jarvis entry point.

Usage:
    python run.py              # interactive chat (type 'exit' to quit)
    python run.py --demo       # run a scripted demo of every feature
    python run.py --once "..." # ask a single question and exit

Requires a provider key, e.g.:
    export LARGESTACK_DEEPSEEK_API_KEY="sk-..."
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make `jarvis` importable when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jarvis.assistant import Jarvis, JarvisReply  # noqa: E402
from jarvis.config import MODEL, has_api_key  # noqa: E402

DEMO_SCRIPT = [
    "Hi Jarvis — who are you and what can you do?",
    "Take a note: buy milk and call the bank tomorrow.",
    "What notes do I have?",
    "Remember that my project deadline is June 20.",
    "What is my project deadline?",
    "What is 23 * 19 + 7?",
    "Please delete all the files in my home folder.",
]


def _print_turn(user: str, out: JarvisReply) -> None:
    print(f"\n\033[1mYou:\033[0m {user}")
    print(f"\033[36mJarvis:\033[0m {out.reply}")
    meta = f"  · tools: {out.tools_used or '—'} · turn ${out.turn_cost:.6f} · total ${out.total_cost:.6f}"
    print(f"\033[90m{meta}\033[0m")


async def run_demo() -> None:
    jarvis = Jarvis()
    print(f"=== Jarvis demo (model: {MODEL}) ===")
    try:
        for msg in DEMO_SCRIPT:
            out = await jarvis.ask(msg)
            _print_turn(msg, out)
    finally:
        await jarvis.close()
    print(f"\n=== Demo complete · total spend ${jarvis.total_cost:.6f} ===")


async def run_once(message: str) -> None:
    jarvis = Jarvis()
    try:
        out = await jarvis.ask(message)
        _print_turn(message, out)
    finally:
        await jarvis.close()


async def run_interactive() -> None:
    jarvis = Jarvis()
    print(f"=== Jarvis (model: {MODEL}) — type 'exit' to quit ===")
    try:
        while True:
            try:
                msg = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if msg.lower() in {"exit", "quit", "bye"}:
                break
            if not msg:
                continue
            out = await jarvis.ask(msg)
            print(f"Jarvis: {out.reply}")
            print(f"\033[90m  · tools: {out.tools_used or '—'} · total ${out.total_cost:.6f}\033[0m")
    finally:
        await jarvis.close()
    print("Bye.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Jarvis assistant on Largestack")
    parser.add_argument("--demo", action="store_true", help="run a scripted feature demo")
    parser.add_argument("--once", metavar="MSG", help="ask one question and exit")
    args = parser.parse_args()

    if not has_api_key():
        print(
            f"No API key for model '{MODEL}'.\n"
            "Set one first, e.g.:  export LARGESTACK_DEEPSEEK_API_KEY=\"sk-...\"",
            file=sys.stderr,
        )
        return 2

    if args.demo:
        asyncio.run(run_demo())
    elif args.once:
        asyncio.run(run_once(args.once))
    else:
        asyncio.run(run_interactive())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
