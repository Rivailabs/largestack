# Jarvis Capstone — Internal Harness Run (honest summary)

> This is an **internal harness run** of `scripts/jarvis_capstone_live.py` — a
> self-graded smoke test on the maintainer's machine. It is **not** independent
> validation, certification, or proof of production readiness.

## Result
- Classification: `REAL-EXTERNAL` (real DeepSeek API calls)
- Passed (all criteria): **No** — 11 of 13 criteria passed
- Harness score: `85/100` (self-graded by the harness, not an external audit)
- Live DeepSeek agent runs: 11 (all completed)
- Duration: ~474s · tokens tracked: 132,288 · actual cost: $0.0171

## Criteria
Passed: live agents completed, team context passing, RAG tool used, memory tool
used, approval-required-for-risky-actions, monitor traces, tokens tracked,
estimated cost available, guardrails enabled, no secret leak, no unsafe action
executed.

Failed:
- `builder_saved_artifacts` — only **2 of 7** expected artifacts were saved.
- `completed_under_5_minutes` — the run took ~8 minutes.

## Honest limitations
- The generated artifacts are **design documents produced by the LLM**, not a
  running Jarvis application. For a real, working assistant built on Largestack,
  see the `jarvis_app/` bundle in this repo (it is tested and runs live).
- Memory in this harness was simulated/local; persistent cross-session memory
  needs a real store and privacy controls.
- Approvals are evidenced via the `request_approval` tool, but a full HITL
  approval UI / work queue is still required.
- Real connectors (calendar, email, filesystem, social, payments, HR, production
  databases) remain intentionally unexecuted.

Raw per-run data is generated locally under `release_evidence/jarvis_capstone_live/`
when you run the harness; it is intentionally **not committed** (see this folder's
README evidence policy).
