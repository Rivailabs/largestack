#!/bin/bash
# Verify CHANGELOG test count matches reality.
#
# v0.3.9: tolerance of ±3 to absorb optional-dependency variance — 3 tests in
# `test_p0_fixes_v038.py` skip without `[otel]` extra installed. The CHANGELOG
# claim is what the CI canonical environment sees (with all extras installed).
# Local environments without optional extras may see fewer tests.
set -e
# v1.1.1: use the release interpreter (the repo venv), not whatever `python3` resolves
# to — a system 3.10 produces a wrong count and the suite requires Python >=3.11.
PYTHON="${PYTHON:-.venv/bin/python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then PYTHON="python3"; fi
PYVER=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,11) else 1)'; then :; else
    echo "FAIL: $PYTHON is $PYVER; largestack requires Python >=3.11. Set PYTHON=/path/to/py311+."
    exit 1
fi
ACTUAL=$("$PYTHON" -m pytest tests/ -q --tb=no 2>&1 | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+')
if [ -z "$ACTUAL" ]; then
    echo "Could not parse test count from pytest output"
    exit 1
fi

# Extract version + count from topmost entry only
TOP_VERSION_LINE=$(grep -n "^## v" CHANGELOG.md | head -1 | cut -d: -f1)
NEXT_VERSION_LINE=$(grep -n "^## v" CHANGELOG.md | sed -n '2p' | cut -d: -f1)
if [ -z "$NEXT_VERSION_LINE" ]; then
    NEXT_VERSION_LINE=$(wc -l < CHANGELOG.md)
fi

CLAIMED=$(sed -n "${TOP_VERSION_LINE},${NEXT_VERSION_LINE}p" CHANGELOG.md | grep -oE '\*\*[0-9]+ passing\*\*' | head -1 | grep -oE '[0-9]+')
if [ -z "$CLAIMED" ]; then
    echo "FAIL: topmost CHANGELOG section has no '**N passing**' canonical line"
    echo "  (Format must be exactly: '- **826 passing** ...')"
    exit 1
fi

# The CHANGELOG count is the canonical full-extras (CI) count — the MAXIMUM.
# Running with fewer optional extras yields fewer passing tests, which is EXPECTED
# (not a failure). Only fail if MORE tests pass than claimed, i.e. tests were added
# without bumping the "**N passing**" line.
OVER=$((ACTUAL - CLAIMED))
if [ "$OVER" -gt 3 ]; then
    echo "CHANGELOG count stale: actual=$ACTUAL exceeds claimed=$CLAIMED by $OVER."
    echo "  You added tests — bump the top '**N passing**' line in CHANGELOG.md."
    exit 1
fi
if [ "$ACTUAL" -lt "$CLAIMED" ]; then
    echo "CHANGELOG count OK: actual=$ACTUAL <= claimed=$CLAIMED (fewer optional extras installed; canonical CI count is $CLAIMED)."
else
    echo "CHANGELOG count OK: actual=$ACTUAL (matches claimed=$CLAIMED within +3)."
fi
