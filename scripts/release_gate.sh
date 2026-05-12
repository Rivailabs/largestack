#!/usr/bin/env bash
# Full LARGESTACK release gate.
#
# Default mode is CI-friendly: it runs all local deterministic gates and skips
# gates that require unavailable external systems (Docker daemon, cloud LLM
# credentials, live vector DBs). Set REQUIRE_DOCKER=1, REQUIRE_CLOUD_E2E=1, or
# REQUIRE_VECTOR_E2E=1 to make those optional gates hard failures.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

run() {
  echo "\n=== $* ==="
  "$@"
}

run python -m compileall -q largestack tests scripts examples
run python scripts/run_pytest_matrix.py tests --timeout "${PYTEST_MATRIX_TIMEOUT:-120}"
run python scripts/smoke_test_e2e.py
run python scripts/scenario_kyc_nbfc.py
run python scripts/scenario_rag_legaltech.py
run python scripts/scenario_breach_dpdp.py
run python scripts/scenarios_100.py
run bash scripts/build_production_wheel.sh

if command -v docker >/dev/null 2>&1; then
  run docker build -t largestack:release-gate .
  if docker compose version >/dev/null 2>&1; then
    run docker compose -f deploy/docker-compose.yml config
  fi
else
  echo "\n=== Docker gate skipped: docker command not found ==="
  if [[ "${REQUIRE_DOCKER:-0}" == "1" ]]; then
    echo "Docker is required but not available" >&2
    exit 20
  fi
fi

if [[ -n "${LARGESTACK_DEEPSEEK_API_KEY:-}" || -n "${LARGESTACK_OPENAI_API_KEY:-}" ]]; then
  run python -m pytest tests/integration/test_deepseek_integration.py tests/integration/test_deepseek_automation.py -q --tb=short
else
  echo "\n=== Cloud provider E2E skipped: set LARGESTACK_DEEPSEEK_API_KEY or LARGESTACK_OPENAI_API_KEY ==="
  if [[ "${REQUIRE_CLOUD_E2E:-0}" == "1" ]]; then
    echo "Cloud provider E2E is required but no provider key is set" >&2
    exit 21
  fi
fi

if [[ -n "${QDRANT_URL:-}" || -n "${LARGESTACK_QDRANT_URL:-}" ]]; then
  run python scripts/vectorstores_e2e.py
else
  echo "\n=== External vector DB E2E skipped: set QDRANT_URL or LARGESTACK_QDRANT_URL ==="
  if [[ "${REQUIRE_VECTOR_E2E:-0}" == "1" ]]; then
    echo "Vector DB E2E is required but no vector DB URL is set" >&2
    exit 22
  fi
fi

echo "\n✅ Release gate completed. Optional infrastructure gates may have been skipped as documented above."
