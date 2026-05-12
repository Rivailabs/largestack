# DeepSeek Build Projects Live Summary

- Classification: `DEEPSEEK-BUILT-PROJECTS+LARGESTACK-LIVE`
- Total projects: `10`
- Passed: `9`
- Failed: `1`
- Score: `90/100`
- DeepSeek/Largestack builds: `9`
- Total tokens: `34637`
- Actual framework cost total: `$0.013616`
- Estimated DeepSeek cost total: `$0.007274`
- Duration: `257.13s`

## Project Results
- `PASS` jarvis_core files=4 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` support_ticket_api files=2 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `FAIL` rag_assistant files=0 attempts=4 compile=True pytest=False acceptance=False budget_exceeded=False
- `PASS` task_app files=3 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` code_reviewer files=2 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` ml_automation files=2 attempts=4 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` website_builder files=3 attempts=2 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` resume_builder files=2 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` hr_interview files=2 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False
- `PASS` video_social_pipeline files=2 attempts=1 compile=True pytest=True acceptance=True budget_exceeded=False

## Strict Review
- This is the strongest build test so far: DeepSeek generated the project code through Largestack, and hidden acceptance checks validated the public APIs.
- Passing here proves bounded multi-project generation, not production readiness.
- Still missing for production: real connectors, encrypted persistent memory, vector RAG, HITL UI, load testing, deployment hardening, browser/a11y testing, and long-running autonomous repair.