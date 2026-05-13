# LARGESTACK Mac Validation Report

Timestamp: `20260512-203121`

| Gate | Result | Evidence | Notes |
| --- | --- | --- | --- |
| Environment | PASS | `initial_python_version.log`, `initial_platform.log`, `initial_git_status_short.log` | Fresh clone from `Rivailabs/largestack`; Python validation venv uses `3.11.15`; no `.env` found. |
| Install | PASS | `step17_final_pip_install_editable_dev_after_builder_fix_elevated.log` | Editable dev install completed from the final tree after adding missing runtime dependency `defusedxml>=0.7.1`. |
| Compile | PASS | `step16_final_compileall_after_builder_fix.log` | `python -m compileall largestack tests examples scripts` passed. |
| Full pytest | PASS | `step16_final_pytest_full_after_builder_fix_elevated.log` | `2510 passed, 23 skipped in 39.58s`. Non-elevated rerun hit sandbox-only writes to `~/.largestack/.kill_switch`; elevated normal Mac run passed. |
| Security | PASS | `step16_final_gitleaks_after_live_autofix.log`, `step3_bandit.log`, `step3_pip_audit.log`, `step16_final_secret_regex_scan_after_live_autofix.log` | gitleaks no leaks; Bandit no medium/high issues; pip-audit clean for third-party deps; no key-shaped strings under this evidence dir. |
| Build/twine | PASS | `step17_final_python_m_build_after_builder_fix_elevated.log`, `step17_final_twine_check_after_builder_fix.log` | Wheel and sdist build clean from the final tree; `twine check dist/*` passed. |
| Docker | PASS | `step4_docker_build.log`, `step4_docker_curl_health_elevated.log` | Docker Desktop running; `/health` returned HTTP 200 and version `1.0.0`; test container removed. |
| Helm | PASS | `step4_helm_lint_largestack.log`, `step4_helm_lint_largestack_agentic_ai.log`, `step4_helm_template_*.yaml` | Both charts linted. `largestack-agentic-ai` requires a dashboard key for template rendering; rendered with test-only value. No Kubernetes install claimed. |
| 48 generated projects local validation | PASS | `step6_generated_projects_validation.json` | Original 48 projects compiled, local pytest passed, imported real Largestack, had README/report, and had no fake Agent/Workflow/Team mocks. |
| +2 BFSI status | PASS for selected BFSI scope | `step15_bfsi_plus2_autofix2_evidence/summary.json`, `step13_bfsi_plus2_autofix2_live.log` | Live DeepSeek generated loan origination and AML projects automatically; both passed with score `99`, failed checks `[]`, reviewer pass. |
| 50 generated projects local validation | PASS | `step15_50_projects_with_auto_bfsi_validation.json`, `step15_validate_50_projects_with_auto_bfsi.log` | `50` found, `50` compiled, `50` local pytest passed, `0` failed, `0` missing app/import/README/report, `0` fake/mock usage. |
| DeepSeek smoke | PASS | `step15_bfsi_plus2_autofix2_evidence/live_deepseek_smoke.json` | Live provider smoke passed before BFSI generation. |
| Remaining blockers | NONE for Mac validation | This report | Non-blocking scope note: the BFSI run was a `2/26` project slice, so its full-suite `final_decision` is correctly `HOLD`; its selected-scope decision is `GO`. |
| Final decision | GO | `FINAL_50_PROJECT_BACKEND_CONFIRMATION.md` | Mac framework/backend and 50 generated project artifacts are validated locally on Mac. |

No commit or push was performed.
