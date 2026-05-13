# +2 BFSI Manual Fix Summary

The live certifier generated both BFSI artifacts:

- `25_bfsi_loan_origination_maker_checker`: generated and certified as pass.
- `26_bfsi_aml_transaction_monitoring`: generated but failed the certifier on pytest, acceptance, reviewer pass, and score.

Manual post-generation fix applied to `26_bfsi_aml_transaction_monitoring/aml_monitoring.py`:

- Support watchlists shaped as `{"blocked_countries": [...], "high_risk_keywords": [...]}` as well as list entries.
- Support transaction country under either `country` or `counterparty_country`.
- Support customer average volume under either `average_monthly_volume` or `avg_monthly_volume`.
- Return `requires_review` from `screen_transaction`.
- Make `draft_sar` honor either `risk` or `risk_level`.
- Make `policy_answer` accept dict documents, cite document names, filter stopwords, and return insufficient evidence for unrelated questions.

Post-fix local validation:

- Pytest: `11 passed` (`step7_bfsi_aml_pytest_after_manual_fix.log`)
- Domain acceptance snippet: `acceptance ok` (`step7_bfsi_aml_acceptance_after_manual_fix.log`)

Release decision on +2 BFSI artifacts:

- They should be added as release evidence only after the generated artifacts are checked in intentionally and the certifier/harness can reproduce a passing result without manual patching.
- Current state proves the +2 specs exist and are fixable, but the automated +2 BFSI generation path is not yet a clean pass.

