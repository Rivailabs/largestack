#!/bin/bash
# Verify CHANGELOG test count matches reality.
#
# v0.3.9: tolerance of ±3 to absorb optional-dependency variance — 3 tests in
# `test_p0_fixes_v038.py` skip without `[otel]` extra installed. The CHANGELOG
# claim is what the CI canonical environment sees (with all extras installed).
# Local environments without optional extras may see fewer tests.
set -e
ACTUAL=$(python3 -m pytest tests/ -q --tb=no 2>&1 | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+')
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

# Compute absolute difference
DIFF=$((ACTUAL - CLAIMED))
if [ "$DIFF" -lt 0 ]; then DIFF=$((-DIFF)); fi

# Tolerance: ±3 to absorb optional-dep variance (OTel SDK skip cases)
if [ "$DIFF" -gt 3 ]; then
    echo "CHANGELOG count out of tolerance: actual=$ACTUAL claimed=$CLAIMED diff=$DIFF (max ±3)"
    echo "  Likely cause: tests added/removed without updating CHANGELOG, OR"
    echo "  multiple optional extras drifted at once. Re-run with all extras."
    exit 1
fi
if [ "$ACTUAL" = "$CLAIMED" ]; then
    echo "CHANGELOG count OK: $ACTUAL (tests/, topmost entry, exact)"
else
    echo "CHANGELOG count OK: $ACTUAL within tolerance of claimed=$CLAIMED (Δ=$DIFF, optional-dep variance)"
fi
