#!/usr/bin/env bash
# Build a production wheel with license keygen stripped.
#
# Usage:
#   bash scripts/build_production_wheel.sh
#
# This produces dist/largestack-<version>-py3-none-any.whl with the
# LicenseValidator.generate_key() method permanently disabled, regardless of
# the LARGESTACK_KEYGEN_ENABLED runtime env var.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LICENSE_FILE="largestack/_core/license.py"
BACKUP="${LICENSE_FILE}.preserve_keygen.bak"

cleanup() {
    if [[ -f "$BACKUP" ]]; then
        mv "$BACKUP" "$LICENSE_FILE"
        echo "✓ Restored keygen-enabled source"
    fi
}
trap cleanup EXIT

# 1. Backup original
cp "$LICENSE_FILE" "$BACKUP"

# 2. Strip keygen — flip the build-time flag
python3 -c "
import sys
src = open('$LICENSE_FILE').read()
old = '_BUILD_STRIPPED = False  # build-time flag; do not edit manually'
new = '_BUILD_STRIPPED = True   # build-time flag; KEYGEN STRIPPED'
if old not in src:
    print('ERROR: build-time flag marker not found in $LICENSE_FILE', file=sys.stderr)
    sys.exit(1)
open('$LICENSE_FILE', 'w').write(src.replace(old, new))
print('✓ Stripped keygen (flag flipped to True)')
"

# 3. Verify
if ! grep -q "_BUILD_STRIPPED = True" "$LICENSE_FILE"; then
    echo "ERROR: strip verification failed" >&2
    exit 1
fi

# 4. Build wheel
echo "Building wheel..."
rm -rf dist/ build/ *.egg-info
python3 -m pip show build >/dev/null 2>&1 || python3 -m pip install --quiet build
python3 -m build --wheel

# 5. Smoke test the built wheel
echo "Verifying wheel does not allow keygen..."
TMPVENV=$(mktemp -d)
python3 -m venv "$TMPVENV"
"$TMPVENV/bin/pip" install --no-deps --quiet dist/*.whl
"$TMPVENV/bin/python" -c "
import importlib.util
import os
import pathlib
import site
import sys

os.environ['LARGESTACK_KEYGEN_ENABLED'] = '1'  # Try to enable runtime
license_path = None
for site_dir in site.getsitepackages():
    candidate = pathlib.Path(site_dir) / 'largestack' / '_core' / 'license.py'
    if candidate.exists():
        license_path = candidate
        break
if license_path is None:
    print('FAIL: installed wheel license.py not found', file=sys.stderr)
    raise SystemExit(1)
spec = importlib.util.spec_from_file_location('largestack_license_check', license_path)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
try:
    mod.LicenseValidator.generate_key(tier='enterprise')
    print('FAIL: keygen succeeded — strip did not work', file=sys.stderr)
    raise SystemExit(1)
except RuntimeError as e:
    if 'disabled in this build' in str(e):
        print('✓ Keygen confirmed disabled in built wheel')
    else:
        print(f'FAIL: unexpected error: {e}', file=sys.stderr)
        raise SystemExit(1)
"
rm -rf "$TMPVENV"

echo ""
echo "✓ Production wheel built: $(ls -1 dist/*.whl)"
echo "  Keygen is permanently disabled in this artifact."
