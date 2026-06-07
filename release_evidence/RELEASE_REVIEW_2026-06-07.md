# Release Review — largestack v1.1.1 — 2026-06-07

Honest beta release-gate evidence. All commands run with the release interpreter
(`.venv/bin/python`, **Python 3.12.13**; the suite requires ≥3.11). Reproduce with the
commands shown under each section.

| # | Gate | Command | Result |
|---|---|---|---|
| 1 | Full test suite | `.venv/bin/python -m pytest tests/ -q` | **2610 passed, 30 skipped** |
| 2 | Ruff lint | `.venv/bin/python -m ruff check largestack tests` | All checks passed |
| 3 | Build + metadata | `python -m build && twine check dist/*` | both artifacts PASSED |
| 3b | Wheel/sdist contamination | `unzip -l dist/*.whl \| grep enterprise-deepseek` | **0** (clean) |
| 4 | Docs | `mkdocs build --strict` | OK (56 nav entries) |
| 5 | Changelog gate | `PYTHON=.venv/bin/python scripts/check_changelog.sh` | OK (actual=2610) |
| 6 | SAST | `bandit -r largestack -lll` | **0 HIGH** |
| 7 | Deps | `pip check` / `pip-audit` | no broken reqs; **no known vulnerabilities** (torch local-build skipped) |
| 8 | Guardrail red-team | `largestack redteam` | core gate **exit 0** (11/11) |
| 9 | Public import | `python -c "import largestack"` (no optional deps) | 83 exports, no error |
| 10 | Secret scan | grep `sk-/ghp_/pypi-` over source | clean — no real credentials |
| 11 | Provider matrix honesty | `provider_support_matrix()` | `anthropic = adapter_only` (not "verified") |
| 12 | OWASP coverage | `owasp_coverage_summary()` | `{covered: 9, partial: 8, not_covered: 0, total: 17}` |

## Raw output

```
## 1. Full test suite
2610 passed, 30 skipped, 1 warning in 99.19s

## 2. Ruff lint
All checks passed!

## 3. Build + twine
Checking dist/largestack-1.1.1-py3-none-any.whl: PASSED
Checking dist/largestack-1.1.1.tar.gz: PASSED
wheel contamination (enterprise-deepseek): 0

## 4. mkdocs --strict
mkdocs --strict: OK (56 nav entries)

## 5. Changelog gate (uses .venv python + requires >=3.11)
CHANGELOG count OK: actual=2610 (matches claimed=2610 within +3).

## 6. Bandit (HIGH)
HIGH issues: 0

## 7. pip check / pip-audit
No broken requirements found.
No known vulnerabilities found

## 8. Red-team core gate
redteam core exit=0

## 9. Public import (no optional deps)
exports: 83

## 10. Secret scan (source)
clean — no real credentials in source

## 11. Provider matrix honesty
anthropic = adapter_only

## 12. OWASP summary
{'covered': 9, 'partial': 8, 'not_covered': 0, 'total': 17}

## Decorator late-tool bug: fixed + regression test
1 passed
```

## Honest gaps shipped with this Beta (documented, not blockers)
- Anthropic adapter implemented but **not live-verified** (no key tested) — `adapter_only`.
- No external pentest / VAPT; no sustained load/soak proof on representative infra.
- Not "battle-tested" (accrues from real production usage over time).
- ML guards (PromptGuard 2, NLI, Presidio) are **opt-in** via env flags.
- `SecureRAGAgent` does not auto-wire Qdrant / SIEM / LangSmith (documented seams).

## Maintainer release steps (outside code)
1. Rotate any credentials shared during development.
2. Push the branch + merge to `main`.
3. Enable PyPI Trusted Publishing, then tag `v1.1.1`.
