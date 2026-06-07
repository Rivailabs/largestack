#!/usr/bin/env python3
"""Run pytest file-by-file with a per-file timeout.

This is a release-gate fallback for constrained CI/sandbox environments where
one global pytest command can hang without revealing the responsible file. It
uses pytest's normal runner, but isolates files so failures/timeouts are clear.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["tests"], help="test paths to discover")
    parser.add_argument("--timeout", type=int, default=120, help="seconds per test file")
    parser.add_argument(
        "--fail-fast", action="store_true", help="stop at first failed/timed-out file"
    )
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(sorted(p.rglob("test_*.py")))
        else:
            print(f"[matrix] missing path: {p}", file=sys.stderr)
            return 2

    if not files:
        print("[matrix] no test files found", file=sys.stderr)
        return 2

    passed: list[Path] = []
    failed: list[tuple[Path, int]] = []
    timed_out: list[Path] = []

    print(f"[matrix] running {len(files)} test file(s), timeout={args.timeout}s")
    for idx, file in enumerate(files, 1):
        print(f"\n[matrix] {idx}/{len(files)} {file}", flush=True)
        cmd = [sys.executable, "-m", "pytest", "-q", str(file), "--tb=short", "--disable-warnings"]
        try:
            proc = subprocess.run(cmd, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            print(f"[matrix] TIMEOUT after {args.timeout}s: {file}", file=sys.stderr, flush=True)
            timed_out.append(file)
            if args.fail_fast:
                break
            continue
        if proc.returncode == 0:
            passed.append(file)
        else:
            failed.append((file, proc.returncode))
            if args.fail_fast:
                break

    print("\n[matrix] summary")
    print(f"  passed files:  {len(passed)}")
    print(f"  failed files:  {len(failed)}")
    print(f"  timed out:     {len(timed_out)}")
    if failed:
        print("\n[matrix] failed files:")
        for file, code in failed:
            print(f"  - {file} (exit {code})")
    if timed_out:
        print("\n[matrix] timed-out files:")
        for file in timed_out:
            print(f"  - {file}")
    return 1 if failed or timed_out else 0


if __name__ == "__main__":
    raise SystemExit(main())
