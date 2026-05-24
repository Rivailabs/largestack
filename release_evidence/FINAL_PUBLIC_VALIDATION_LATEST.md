# Final Public Validation

Generated: 2026-05-24T17:27:40Z
Log root: `/tmp/largestack-final-validate-20260524-225318`
Summary TSV: `/tmp/largestack-final-validate-20260524-225318/summary.tsv`

This is the curated public summary. Raw logs stay outside the git tree and
should be attached as release/CI artifacts only when needed.

| Step | Status | Log |
|---|---|---|
| `python_version` | PASS | `/tmp/largestack-final-validate-20260524-225318/python_version.log` |
| `toml_parse` | PASS | `/tmp/largestack-final-validate-20260524-225318/toml_parse.log` |
| `compileall` | PASS | `/tmp/largestack-final-validate-20260524-225318/compileall.log` |
| `memory_unit` | PASS | `/tmp/largestack-final-validate-20260524-225318/memory_unit.log` |
| `full_pytest` | PASS | `/tmp/largestack-final-validate-20260524-225318/full_pytest.log` |
| `deepseek_live_tests` | SKIP | `/tmp/largestack-final-validate-20260524-225318/deepseek_live_tests.log` |
| `example_examples_00_offline_test_model.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_00_offline_test_model.py.log` |
| `example_examples_rag_basic_rag_basic.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_rag_basic_rag_basic.py.log` |
| `example_examples_01_hello_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_01_hello_main.py.log` |
| `example_examples_02_tools_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_02_tools_main.py.log` |
| `example_examples_03_team_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_03_team_main.py.log` |
| `example_examples_04_guards_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_04_guards_main.py.log` |
| `example_examples_05_rag_knowledge_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_05_rag_knowledge_main.py.log` |
| `example_examples_06_streaming_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_06_streaming_main.py.log` |
| `example_examples_07_structured_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_07_structured_main.py.log` |
| `example_examples_09_multi_provider_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_09_multi_provider_main.py.log` |
| `example_examples_10_full_app_main.py` | PASS | `/tmp/largestack-final-validate-20260524-225318/example_examples_10_full_app_main.py.log` |
| `smoke_e2e` | PASS | `/tmp/largestack-final-validate-20260524-225318/smoke_e2e.log` |
| `scenario_kyc_nbfc` | PASS | `/tmp/largestack-final-validate-20260524-225318/scenario_kyc_nbfc.log` |
| `scenario_rag_legaltech` | PASS | `/tmp/largestack-final-validate-20260524-225318/scenario_rag_legaltech.log` |
| `scenario_breach_dpdp` | PASS | `/tmp/largestack-final-validate-20260524-225318/scenario_breach_dpdp.log` |
| `bandit_medium_high` | PASS | `/tmp/largestack-final-validate-20260524-225318/bandit_medium_high.log` |
| `pip_audit` | PASS | `/tmp/largestack-final-validate-20260524-225318/pip_audit.log` |
| `gitleaks_no_git` | PASS | `/tmp/largestack-final-validate-20260524-225318/gitleaks_no_git.log` |
| `package_build` | PASS | `/tmp/largestack-final-validate-20260524-225318/package_build.log` |
| `twine_check` | PASS | `/tmp/largestack-final-validate-20260524-225318/twine_check.log` |
| `docker_root_build` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_root_build.log` |
| `docker_deploy_build` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_deploy_build.log` |
| `docker_runtime_start` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_runtime_start.log` |
| `docker_health` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_health.log` |
| `docker_metrics_auth_ok` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_metrics_auth_ok.log` |
| `docker_metrics_auth_bad` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_metrics_auth_bad.log` |
| `docker_compose_config` | PASS | `/tmp/largestack-final-validate-20260524-225318/docker_compose_config.log` |
| `helm_lint` | PASS | `/tmp/largestack-final-validate-20260524-225318/helm_lint.log` |

Result: **PASS** for required gates. Review SKIP rows for optional/provider gates.
