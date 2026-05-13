# LARGESTACK Mac Fix Validation Report

Timestamp: `20260512-203121`
Host: macOS arm64 (`Darwin`, `macOS-15.1-arm64-arm-64bit`)
Validation venv: `.venv-mac`, Python `3.11.15`

Final decision: `GO for Mac validation`; `full-suite release GO still requires running the full selected suite, not only a slice`.

No commit or push was performed.

| Priority | Fix / Gate | Status | Evidence | Result |
| ---: | --- | --- | --- | --- |
| 0 | Editable dev install | PASS | `step17_final_pip_install_editable_dev_after_builder_fix_elevated.log` | Final tree installed successfully into `.venv-mac`. |
| 1 | FAISS persistent test on Mac ARM | PASS | `step1_pytest_v090_vectorstores_after_subprocess_fix.log`, `step16_final_pytest_full_after_builder_fix_elevated.log` | Replaced in-process Mac arm64 FAISS persistent tests with fresh subprocess execution. FAISS still runs; it is not skipped. Full unfiltered pytest now passes: `2510 passed, 23 skipped in 39.58s`. |
| 2 | Duplicate docs, keep lowercase | PASS | `step2_doc_index_before.log`, `step2_doc_paths_after.log`, `step2_git_status_docs_after.log` | Removed uppercase duplicate docs from Git index with `git rm --cached`; lowercase tracked docs remain: `docs/deployment.md`, `docs/quickstart.md`, `docs/security.md`, `docs/troubleshooting.md`. Uppercase deletions are staged, not committed. |
| 3 | Install and rerun gitleaks | PASS | `step3_brew_install_gitleaks.log`, `step3_gitleaks_version.log`, `step3_gitleaks_detect_no_git.log`, `step16_final_gitleaks_after_live_autofix.log` | Installed `gitleaks 8.30.1`. Source scan completed: `no leaks found`. Final scan after live-key runs also clean. |
| 3 | Bandit / pip-audit rerun | PASS | `step3_bandit.log`, `step3_pip_audit.log` | Bandit found 0 medium/high issues. pip-audit found no known third-party vulnerabilities; local editable `largestack` skipped because it is not on PyPI. |
| 4 | Docker Desktop and Docker gate | PASS | `step4_docker_build.log`, `step4_docker_run.log`, `step4_docker_curl_health_elevated.log`, `step4_docker_stop.log`, `step4_docker_rm.log` | Docker Desktop started. Image built as `largestack:mac-test`. Container `/health` returned `HTTP/1.1 200 OK` with version `1.0.0`. Test container stopped and removed. |
| 5 | Install Helm and rerun Helm | PASS with required value note | `step4_brew_install_helm.log`, `step4_helm_version.log`, `step4_helm_lint_*.log`, `step4_helm_template_*.yaml` | Installed Helm `v4.1.4`. Both charts linted successfully. `deploy/helm/largestack` templated directly. `deploy/helm/largestack-agentic-ai` requires `secrets.dashboardKey`; direct template fails as designed, and template passes with test-only `--set secrets.dashboardKey=test-dashboard-key-for-render-only`. No Kubernetes install claimed. |
| 6 | +2 BFSI artifacts decision | PASS for selected BFSI scope | `step13_bfsi_plus2_autofix2_live.log`, `step15_bfsi_plus2_autofix2_evidence/summary.json`, `step15_validate_50_projects_with_auto_bfsi.log` | Decision: yes, +2 BFSI artifacts should be added for a defensible 50-project claim. After fixing the generator recovery path and tightening AML citation requirements, live DeepSeek generated both BFSI projects automatically; both passed with score `99`, `scope_decision=GO`, and local 50-project validation passed. |
| Extra | Compile | PASS | `step5_compileall.log` | `python -m compileall largestack tests examples scripts` passed. |
| Extra | Package build/twine | PASS | `step17_final_python_m_build_after_builder_fix_elevated.log`, `step17_final_twine_check_after_builder_fix.log` | Built wheel + sdist from the final tree; `twine check dist/*` passed. |
| Extra | 50 generated projects local validation | PASS | `step15_validate_50_projects_with_auto_bfsi.log`, `step15_50_projects_with_auto_bfsi_validation.json`, `step6_project_logs/` | Validated from copied scratch dirs to avoid mutating source artifacts: `50` found, `50` compiled, `50` pytest passed, `0` failed, `0` missing app/README/report/imports, `0` fake/mock framework usage. |
| Extra | Secret hygiene after live runs | PASS | `step16_final_secret_regex_scan_after_live_autofix.log`, `step16_final_gitleaks_after_live_autofix.log` | No `sk-...` key-shaped strings found under this evidence directory; final gitleaks scan clean. |

## Code Changes Made

- `pyproject.toml`: added `defusedxml>=0.7.1`, because `largestack._core.parsers` imports it and pytest collection failed without it.
- `tests/unit/test_v090_vectorstores_more.py`: added macOS arm64 subprocess execution for FAISS persistent tests to avoid full-suite native `faiss-cpu` segfault while still testing FAISS behavior.
- `largestack/autonomous_builder.py`: hardened JSON extraction, requested provider JSON mode, regenerated instead of patching empty projects, and improved hidden-acceptance feedback.
- `scripts/largestack_real_feature_certify.py`: tightened AML citation contract and split partial-slice `scope_decision` from full-suite `final_decision`.
- `tests/unit/test_autonomous_builder.py` and `tests/unit/test_real_feature_certify.py`: added regression coverage for these fixes.
- Git index: staged removal of uppercase duplicate docs, keeping lowercase canonical docs.

## +2 BFSI Decision

Add the +2 BFSI artifacts from the automated generation/certification path.

Current evidence:

- `bfsi_loan_origination_maker_checker`: live generated, certified pass, score `99`.
- `bfsi_aml_transaction_monitoring`: live generated, certified pass, score `99`.

Strict release interpretation:

- The selected +2 BFSI scope is GO.
- Do not claim a full 26-project feature-suite GO from this BFSI slice alone; the harness records that distinction as `scope_decision=GO` and `final_decision=HOLD` for the partial run.

## Final Git Status Summary

Expected uncommitted changes:

- Staged uppercase doc deletions:
  - `docs/DEPLOYMENT.md`
  - `docs/QUICKSTART.md`
  - `docs/SECURITY.md`
  - `docs/TROUBLESHOOTING.md`
- Modified source:
  - `largestack/autonomous_builder.py`
  - `pyproject.toml`
  - `scripts/largestack_real_feature_certify.py`
  - `tests/unit/test_autonomous_builder.py`
  - `tests/unit/test_real_feature_certify.py`
  - `tests/unit/test_v090_vectorstores_more.py`
- New evidence:
  - `release_evidence/final_95_plus/mac-bfsi-plus2-autofix2-20260512-203121/`
  - `release_evidence/mac_validation/`
