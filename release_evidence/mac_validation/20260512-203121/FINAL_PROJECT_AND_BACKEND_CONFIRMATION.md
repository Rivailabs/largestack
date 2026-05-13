# Final Mac Project And Backend Confirmation

Evidence timestamp: `20260512-203121`

## Bottom Line

- LARGESTACK backend/framework gates on Mac: `PASS`.
- Existing generated real projects in repo: `48/48 PASS` locally on Mac.
- All 50 fully automatic LLM-built project claim: `HOLD`, because `26_bfsi_aml_transaction_monitoring` failed the automated certifier and only passed after manual repair.
- No commit or push was performed.

## Backend / Framework Gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Install | PASS | `.venv-mac`, editable install; `defusedxml` dependency fix included |
| Compile | PASS | `step5_compileall.log` |
| Full pytest | PASS: `2507 passed, 23 skipped` | `step1_pytest_full_after_faiss_fix.log` |
| Security secrets | PASS: gitleaks no leaks | `final_gitleaks_detect_no_git.log` |
| Bandit | PASS: 0 medium/high | `step3_bandit.log` |
| pip-audit | PASS: no known third-party vulns | `step3_pip_audit.log` |
| Package build | PASS: wheel + sdist | `step5_python_m_build.log` |
| Twine check | PASS | `step5_twine_check.log` |
| Docker backend health | PASS: `/health` returned 200, version 1.0.0 | `step4_docker_curl_health_elevated.log` |
| Helm | PASS: lint/template, chart secret value required for render | `step4_helm_*` logs |
| Duplicate docs | FIXED in index: lowercase kept | `step2_doc_paths_after.log` |

## Existing 48 Project Artifact Validation

Every row below compiled, ran local pytest, had `largestack_app.py`, imported real `largestack`, had README/report, and had zero fake Agent/Workflow/Team mock definitions.

| # | Suite | Project | Features | Score | Result |
| ---: | --- | --- | --- | ---: | --- |
| 1 | 20260512-realfeatures24-final06 | `01_support_ticket_automation_api` | agent_tool_cost, tool_policy_approval | 99 | PASS |
| 2 | 20260512-realfeatures24-final06 | `02_simple_crm` | team_sequential, memory_isolation | 100 | PASS |
| 3 | 20260512-realfeatures24-final06 | `03_task_manager` | workflow_dag, observability_trace | 99 | PASS |
| 4 | 20260512-realfeatures24-final06 | `04_expense_tracker` | rag_citations, guardrails_pii | 99 | PASS |
| 5 | 20260512-realfeatures24-final06 | `05_inventory_tracker` | orchestrator_router, team_parallel | 99 | PASS |
| 6 | 20260512-realfeatures24-final06 | `06_appointment_booking` | typed_decorator_api, memory_isolation | 99 | PASS |
| 7 | 20260512-realfeatures24-final06 | `07_lead_capture_app` | orchestrator_map_reduce, agent_tool_cost | 99 | PASS |
| 8 | 20260512-realfeatures24-final06 | `08_document_upload_extraction_portal` | rag_citations, memory_isolation | 99 | PASS |
| 9 | 20260512-realfeatures24-final06 | `09_mini_rag_assistant_api` | workflow_dag, rag_citations | 99 | PASS |
| 10 | 20260512-realfeatures24-final06 | `10_agent_workflow_dashboard` | guardrails_pii, observability_trace | 99 | PASS |
| 11 | 20260512-realfeatures24-final06 | `11_ai_security_gateway_website` | team_parallel, tool_policy_approval | 99 | PASS |
| 12 | 20260512-realfeatures24-final06 | `12_resume_builder` | typed_decorator_api, workflow_dag | 99 | PASS |
| 13 | 20260512-realfeatures24-final06 | `13_hr_interview_scorer` | agent_tool_cost, guardrails_pii | 99 | PASS |
| 14 | 20260512-realfeatures24-final06 | `14_code_reviewer_fixer` | orchestrator_router, memory_isolation | 99 | PASS |
| 15 | 20260512-realfeatures24-final06 | `15_ml_automation_baseline` | orchestrator_map_reduce, team_sequential | 99 | PASS |
| 16 | 20260512-realfeatures24-final06 | `16_video_social_pipeline` | rag_citations, observability_trace | 99 | PASS |
| 17 | 20260512-realfeatures24-final06 | `17_jarvis_memory_planner_approval_core` | workflow_dag, tool_policy_approval | 99 | PASS |
| 18 | 20260512-realfeatures24-final06 | `18_fintech_kyc_nbfc_workflow` | typed_decorator_api, guardrails_pii | 99 | PASS |
| 19 | 20260512-realfeatures24-final06 | `19_legaltech_rag_assistant` | team_parallel, memory_isolation | 99 | PASS |
| 20 | 20260512-realfeatures24-final06 | `20_dpdp_breach_response_workflow` | orchestrator_router, agent_tool_cost | 99 | PASS |
| 21 | 20260512-realfeatures24-final06 | `21_background_verification_portal` | rag_citations, tool_policy_approval | 99 | PASS |
| 22 | 20260512-realfeatures24-final06 | `22_trading_app_risk_disclaimer` | workflow_dag, team_sequential | 99 | PASS |
| 23 | 20260512-realfeatures24-final06 | `23_esign_document_approval_workflow` | typed_decorator_api, observability_trace | 99 | PASS |
| 24 | 20260512-realfeatures24-final06 | `24_hal_mosaic_ticket_domain_workflow` | orchestrator_map_reduce, guardrails_pii | 99 | PASS |
| 25 | 20260512-b2b-agentic24-final02 | `01_b2b_sales_forecast_copilot` | agent_tool_cost, tool_policy_approval | 99 | PASS |
| 26 | 20260512-b2b-agentic24-final02 | `02_b2b_revenue_ops_pipeline_agent` | team_sequential, memory_isolation | 99 | PASS |
| 27 | 20260512-b2b-agentic24-final02 | `03_b2b_customer_success_health_monitor` | workflow_dag, observability_trace | 99 | PASS |
| 28 | 20260512-b2b-agentic24-final02 | `04_b2b_vendor_risk_assessment_agent` | rag_citations, guardrails_pii | 99 | PASS |
| 29 | 20260512-b2b-agentic24-final02 | `05_b2b_procurement_contract_triage` | orchestrator_router, team_parallel | 99 | PASS |
| 30 | 20260512-b2b-agentic24-final02 | `06_b2b_invoice_reconciliation_agent` | typed_decorator_api, memory_isolation | 99 | PASS |
| 31 | 20260512-b2b-agentic24-final02 | `07_b2b_accounts_receivable_collections_agent` | orchestrator_map_reduce, agent_tool_cost | 99 | PASS |
| 32 | 20260512-b2b-agentic24-final02 | `08_b2b_compliance_evidence_mapper` | rag_citations, memory_isolation | 99 | PASS |
| 33 | 20260512-b2b-agentic24-final02 | `09_b2b_incident_response_war_room` | workflow_dag, rag_citations | 99 | PASS |
| 34 | 20260512-b2b-agentic24-final02 | `10_b2b_enterprise_knowledge_support_copilot` | guardrails_pii, observability_trace | 99 | PASS |
| 35 | 20260512-b2b-agentic24-final02 | `11_b2b_field_service_dispatch_optimizer` | team_parallel, tool_policy_approval | 99 | PASS |
| 36 | 20260512-b2b-agentic24-final02 | `12_b2b_qa_regression_planner_agent` | typed_decorator_api, workflow_dag | 99 | PASS |
| 37 | 20260512-b2b-agentic24-final02 | `13_b2b_cloud_cost_anomaly_assistant` | agent_tool_cost, guardrails_pii | 99 | PASS |
| 38 | 20260512-b2b-agentic24-final02 | `14_b2b_sales_call_coaching_agent` | orchestrator_router, memory_isolation | 99 | PASS |
| 39 | 20260512-b2b-agentic24-final02 | `15_b2b_renewal_churn_forecaster` | orchestrator_map_reduce, team_sequential | 99 | PASS |
| 40 | 20260512-b2b-agentic24-final02 | `16_b2b_partner_onboarding_approval` | rag_citations, observability_trace | 99 | PASS |
| 41 | 20260512-b2b-agentic24-final02 | `17_b2b_supply_chain_delay_predictor` | workflow_dag, tool_policy_approval | 99 | PASS |
| 42 | 20260512-b2b-agentic24-final02 | `18_b2b_data_privacy_dsr_automation` | typed_decorator_api, guardrails_pii | 99 | PASS |
| 43 | 20260512-b2b-agentic24-final02 | `19_b2b_audit_control_testing_assistant` | team_parallel, memory_isolation | 99 | PASS |
| 44 | 20260512-b2b-agentic24-final02 | `20_b2b_enterprise_rfp_response_builder` | orchestrator_router, agent_tool_cost | 99 | PASS |
| 45 | 20260512-b2b-agentic24-final02 | `21_b2b_product_feedback_intelligence` | rag_citations, tool_policy_approval | 99 | PASS |
| 46 | 20260512-b2b-agentic24-final02 | `22_b2b_workforce_capacity_planner` | workflow_dag, team_sequential | 99 | PASS |
| 47 | 20260512-b2b-agentic24-final02 | `23_b2b_contract_obligation_tracker` | typed_decorator_api, observability_trace | 99 | PASS |
| 48 | 20260512-b2b-agentic24-final02 | `24_b2b_msp_ticket_router_sla_agent` | orchestrator_map_reduce, guardrails_pii | 99 | PASS |

## +2 BFSI Status

| Project | Features | Auto Certifier | Score | Failed Checks | Current Local Status |
| --- | --- | --- | ---: | --- | --- |
| `bfsi_loan_origination_maker_checker` | workflow_dag, tool_policy_approval, guardrails_pii | PASS | 99 | none | PASS |
| `bfsi_aml_transaction_monitoring` | orchestrator_router, rag_citations, observability_trace | FAIL | 62 | pytest, acceptance, reviewer_not_passed, score_below_90 | PASS after manual repair |

## Strict Confirmation

- Backend is fine on Mac based on framework tests, Docker health, packaging, and security gates.
- The 48 checked-in real project artifacts are fine on Mac and verified against real LARGESTACK imports.
- The +2 BFSI direction is correct, but the automated LLM build path is not yet perfect. Final 50/50 should wait until AML passes the certifier without manual intervention.
