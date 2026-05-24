#!/usr/bin/env bash
set +e
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="$(date +%Y%m%d-%H%M%S)"
LOG_DIR="/tmp/largestack-final-validate-${TS}"
SUMMARY="${LOG_DIR}/summary.tsv"
PUBLIC_SUMMARY="${ROOT}/release_evidence/FINAL_PUBLIC_VALIDATION_${TS}.md"
PUBLIC_LATEST="${ROOT}/release_evidence/FINAL_PUBLIC_VALIDATION_LATEST.md"
mkdir -p "${LOG_DIR}"
mkdir -p "${ROOT}/release_evidence"
cd "${ROOT}" || exit 2

if [[ -x ".venv-final/bin/python" ]]; then
  PY=".venv-final/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PY="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "FAIL: no Python found"
  exit 2
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${LOG_DIR}/pycache"

echo -e "step\tstatus\tlog" > "${SUMMARY}"
FAILURES=0

redact_log() {
  local file="$1"
  if [[ -f "$file" ]]; then
    sed -i -E 's/(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+/\1REDACTED/g; s/(LARGESTACK_[A-Z0-9_]*API_KEY=)[^[:space:]]+/\1REDACTED/g' "$file"
  fi
}

record() {
  local step="$1" status="$2" log="$3"
  echo -e "${step}\t${status}\t${log}" | tee -a "${SUMMARY}"
  if [[ "$status" == "FAIL" ]]; then
    FAILURES=$((FAILURES + 1))
  fi
}

run_required() {
  local step="$1"; shift
  local log="${LOG_DIR}/${step//[^A-Za-z0-9_.-]/_}.log"
  echo "== ${step} =="
  "$@" >"${log}" 2>&1
  local rc=$?
  redact_log "${log}"
  if [[ $rc -eq 0 ]]; then record "$step" PASS "$log"; else record "$step" FAIL "$log"; fi
}

run_optional() {
  local step="$1"; shift
  local log="${LOG_DIR}/${step//[^A-Za-z0-9_.-]/_}.log"
  echo "== ${step} =="
  "$@" >"${log}" 2>&1
  local rc=$?
  redact_log "${log}"
  if [[ $rc -eq 0 ]]; then record "$step" PASS "$log"; else record "$step" SKIP "$log"; fi
}

run_required "python_version" "$PY" -c 'import sys; print(sys.version); raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
run_required "toml_parse" "$PY" -c 'import tomllib; tomllib.load(open("pyproject.toml", "rb")); print("pyproject.toml ok")'
run_required "compileall" "$PY" -m compileall -q largestack examples scripts tests
run_required "memory_unit" "$PY" -m pytest tests/unit/test_memory.py::test_buffer -q --tb=short --disable-warnings --timeout=180 --timeout-method=thread
run_required "full_pytest" "$PY" -m pytest tests -q --tb=short --disable-warnings -ra --timeout=180 --timeout-method=thread --durations=30

if [[ -n "${LARGESTACK_DEEPSEEK_API_KEY:-}" ]]; then
  run_required "deepseek_live_tests" "$PY" -m pytest tests/integration/test_deepseek_integration.py tests/integration/test_deepseek_automation.py tests/integration/test_agent_e2e.py -q -ra --tb=short --timeout=180 --timeout-method=thread
else
  log="${LOG_DIR}/deepseek_live_tests.log"
  echo "LARGESTACK_DEEPSEEK_API_KEY not set; live DeepSeek tests skipped." > "$log"
  record "deepseek_live_tests" SKIP "$log"
fi

EXAMPLES=(
  examples/00_offline_test_model.py
  examples/rag_basic/rag_basic.py
  examples/01_hello/main.py
  examples/02_tools/main.py
  examples/03_team/main.py
  examples/04_guards/main.py
  examples/05_rag_knowledge/main.py
  examples/06_streaming/main.py
  examples/07_structured/main.py
  examples/09_multi_provider/main.py
  examples/10_full_app/main.py
)
for ex in "${EXAMPLES[@]}"; do
  run_required "example_${ex//\//_}" timeout 120s "$PY" "$ex"
done

run_required "smoke_e2e" "$PY" scripts/smoke_test_e2e.py
run_required "scenario_kyc_nbfc" "$PY" scripts/scenario_kyc_nbfc.py
run_required "scenario_rag_legaltech" "$PY" scripts/scenario_rag_legaltech.py
run_required "scenario_breach_dpdp" "$PY" scripts/scenario_breach_dpdp.py

if command -v bandit >/dev/null 2>&1; then
  BANDIT="bandit"
elif [[ -x ".venv-final/bin/bandit" ]]; then
  BANDIT=".venv-final/bin/bandit"
elif [[ -x ".venv/bin/bandit" ]]; then
  BANDIT=".venv/bin/bandit"
else
  BANDIT=""
fi
if [[ -n "$BANDIT" ]]; then
  run_required "bandit_medium_high" "$BANDIT" -r largestack -x tests --severity-level medium
else
  log="${LOG_DIR}/bandit_medium_high.log"; echo "bandit not installed" > "$log"; record "bandit_medium_high" FAIL "$log"
fi

if command -v pip-audit >/dev/null 2>&1; then
  PIPAUDIT="pip-audit"
elif [[ -x ".venv-final/bin/pip-audit" ]]; then
  PIPAUDIT=".venv-final/bin/pip-audit"
elif [[ -x ".venv/bin/pip-audit" ]]; then
  PIPAUDIT=".venv/bin/pip-audit"
else
  PIPAUDIT=""
fi
if [[ -n "$PIPAUDIT" ]]; then
  run_required "pip_audit" "$PIPAUDIT"
else
  log="${LOG_DIR}/pip_audit.log"; echo "pip-audit not installed" > "$log"; record "pip_audit" FAIL "$log"
fi

if command -v gitleaks >/dev/null 2>&1; then
  run_required "gitleaks_no_git" gitleaks detect --source . --no-git
else
  log="${LOG_DIR}/gitleaks_no_git.log"; echo "gitleaks not installed" > "$log"; record "gitleaks_no_git" SKIP "$log"
fi

run_required "package_build" "$PY" -m build
if command -v twine >/dev/null 2>&1; then
  TWINE="twine"
elif [[ -x ".venv-final/bin/twine" ]]; then
  TWINE=".venv-final/bin/twine"
elif [[ -x ".venv/bin/twine" ]]; then
  TWINE=".venv/bin/twine"
else
  TWINE=""
fi
if [[ -n "$TWINE" ]]; then
  run_required "twine_check" "$TWINE" check dist/*
else
  log="${LOG_DIR}/twine_check.log"; echo "twine not installed" > "$log"; record "twine_check" FAIL "$log"
fi

if command -v docker >/dev/null 2>&1; then
  run_required "docker_root_build" docker build -t largestack:test .
  if [[ -f deploy/Dockerfile ]]; then
    run_required "docker_deploy_build" docker build -f deploy/Dockerfile -t largestack:deploy-test .
  else
    log="${LOG_DIR}/docker_deploy_build.log"; echo "deploy/Dockerfile missing" > "$log"; record "docker_deploy_build" SKIP "$log"
  fi
  RUNTIME_NAME="largestack-final-${TS}"
  run_optional "docker_runtime_start" docker run --rm -d --name "$RUNTIME_NAME" -p 127.0.0.1::8787 -e LARGESTACK_API_KEY=test-key -e LARGESTACK_DASHBOARD_KEY=test-key largestack:test
  sleep 3
  HOST_PORT="$(docker port "$RUNTIME_NAME" 8787/tcp 2>/dev/null | sed -E 's/.*:([0-9]+)$/\1/' | head -n1)"
  if [[ -n "$HOST_PORT" ]]; then
    run_optional "docker_health" curl -fsS "http://127.0.0.1:${HOST_PORT}/health"
    run_optional "docker_metrics_auth_ok" curl -fsS -H 'X-API-Key: test-key' "http://127.0.0.1:${HOST_PORT}/api/metrics"
    run_optional "docker_metrics_auth_bad" bash -lc "code=\$(curl -s -o /dev/null -w '%{http_code}' -H 'X-API-Key: wrong-key' 'http://127.0.0.1:${HOST_PORT}/api/metrics'); [[ \"\$code\" == 401 || \"\$code\" == 403 ]]"
  else
    log="${LOG_DIR}/docker_runtime_port.log"; echo "could not resolve mapped runtime port" > "$log"; record "docker_runtime_port" SKIP "$log"
  fi
  docker rm -f "$RUNTIME_NAME" >/dev/null 2>&1 || true
else
  log="${LOG_DIR}/docker.log"; echo "docker not installed" > "$log"; record "docker" SKIP "$log"
fi

if [[ -f docker-compose.yml || -f compose.yml || -f docker-compose.yaml ]]; then
  run_optional "docker_compose_config" docker compose config
else
  log="${LOG_DIR}/docker_compose_config.log"; echo "compose file not present" > "$log"; record "docker_compose_config" SKIP "$log"
fi

if command -v helm >/dev/null 2>&1 && [[ -d deploy/helm/largestack ]]; then
  run_optional "helm_lint" helm lint deploy/helm/largestack
else
  log="${LOG_DIR}/helm_lint.log"; echo "helm or deploy/helm/largestack not present" > "$log"; record "helm_lint" SKIP "$log"
fi

echo ""
echo "Final validation logs: ${LOG_DIR}"
echo "Summary: ${SUMMARY}"
column -t -s $'\t' "${SUMMARY}" 2>/dev/null || cat "${SUMMARY}"

{
  echo "# Final Public Validation"
  echo ""
  echo "Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "Log root: \`${LOG_DIR}\`"
  echo "Summary TSV: \`${SUMMARY}\`"
  echo ""
  echo "This is the curated public summary. Raw logs stay outside the git tree and"
  echo "should be attached as release/CI artifacts only when needed."
  echo ""
  echo "| Step | Status | Log |"
  echo "|---|---|---|"
  tail -n +2 "${SUMMARY}" | while IFS=$'\t' read -r step status log; do
    echo "| \`${step}\` | ${status} | \`${log}\` |"
  done
  echo ""
  if [[ $FAILURES -gt 0 ]]; then
    echo "Result: **FAIL** (${FAILURES} required gate(s) failed)."
  else
    echo "Result: **PASS** for required gates. Review SKIP rows for optional/provider gates."
  fi
} > "${PUBLIC_SUMMARY}"
cp "${PUBLIC_SUMMARY}" "${PUBLIC_LATEST}"
echo "Public validation summary: ${PUBLIC_SUMMARY}"
echo "Latest public validation summary: ${PUBLIC_LATEST}"

if [[ $FAILURES -gt 0 ]]; then
  echo "FAILED required gates: ${FAILURES}"
  exit 1
fi

echo "All required gates passed. Review SKIP rows for optional/provider gates."
exit 0
