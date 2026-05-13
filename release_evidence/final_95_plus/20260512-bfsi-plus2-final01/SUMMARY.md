# LARGESTACK +2 BFSI Curated Artifact Validation

- Decision: `GO_FOR_LOCAL_ARTIFACT_VALIDATION`
- Projects: `2/2`
- Local pytest: pass for both projects
- Real LARGESTACK imports: pass for both projects
- Fake Agent/Workflow/Team mocks: none found

| # | Project | Features | Pass | Score |
|---:|---|---|---:|---:|
| 25 | bfsi_loan_origination_maker_checker | workflow_dag, tool_policy_approval, guardrails_pii | true | 99 |
| 26 | bfsi_aml_transaction_monitoring | orchestrator_router, rag_citations, observability_trace | true | 99 |

Strict note: this is curated local artifact validation. The live DeepSeek certifier retry for AML still failed automatically, so this should not be represented as a fully automatic LLM generation pass.
