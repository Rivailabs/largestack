# Final 95+ Certification

Use this gate only for the final release decision. It is stricter than normal
pytest because it combines local validation, live DeepSeek behavior, generated
project quality, security, Docker/runtime, and release evidence in one run.

## Secret Handling

Rotate any API key that was pasted into chat, logs, tickets, screenshots, or
documents. The final run must use a fresh key from the shell or CI secret store:

```bash
export LARGESTACK_DEEPSEEK_API_KEY="REDACTED_ROTATED_KEY"
```

Do not pass keys as command arguments. Do not commit keys to files. The
certification harness redacts logs, but a pasted key must still be considered
exposed.

## Command

```bash
python scripts/final_95_plus_certify.py
```

The run writes evidence under:

```text
release_evidence/final_95_plus/<timestamp>/
```

Important outputs:

- `SUMMARY.md`: human-readable decision, scores, gates, projects, blockers
- `summary.json`: machine-readable release decision
- `projects.csv`: 24 generated project scores and failure summaries
- `project_reports/*.json`: per-project build, validation, security, and reviewer evidence
- `logs/*.log`: redacted command logs

## Required Result

Final deployment stays on `HOLD` unless all of these are true:

- Local release validation passes with zero required skips.
- DeepSeek live project generation runs with the rotated key.
- All 24 generated projects score at least `90/100`.
- The generated project suite average is at least `95/100`.
- Security gates pass: source secret scan, security tests, Bandit/pip-audit/gitleaks through the baseline validator.
- Docker build, health, metrics auth success/failure, and cleanup pass on the host.
- SaaS/BFSI targets are not marked `GO` without soak/load/compliance evidence.

## Debug Runs

Short debug runs are allowed while developing the harness, but they are not
release evidence:

```bash
python scripts/final_95_plus_certify.py --skip-baseline --no-cleanup --project-limit 1
```

Only the full command without debug flags can certify a release.
