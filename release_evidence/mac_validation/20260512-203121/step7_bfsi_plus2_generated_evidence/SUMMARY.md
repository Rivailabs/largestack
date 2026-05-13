# LARGESTACK real-feature 26-Project Certification

- Decision: `HOLD`
- Live DeepSeek smoke: `True`
- Projects: `2/26`
- Project minimum score: `90`
- Suite minimum average: `95.0`
- Suite average: `80.5`

## Project Results

| # | Project | Features | Pass | Score | Failed Checks |
|---:|---|---|---:|---:|---|
| 1 | bfsi_loan_origination_maker_checker | workflow_dag, tool_policy_approval, guardrails_pii | True | 99 |  |
| 2 | bfsi_aml_transaction_monitoring | orchestrator_router, rag_citations, observability_trace | False | 62 | pytest, acceptance, reviewer_not_passed, score_below_90 |

## Blockers

- `BUG` bfsi_aml_transaction_monitoring: pytest, acceptance, reviewer_not_passed, score_below_90. Open `/Users/sachiths/largestack/release_evidence/final_95_plus/mac-bfsi-plus2-20260512-203121/project_reports/26_bfsi_aml_transaction_monitoring.json` and repair/rerun.
