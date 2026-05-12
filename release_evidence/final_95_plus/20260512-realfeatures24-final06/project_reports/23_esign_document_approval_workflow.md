# esign_document_approval_workflow

- Status: `PASS`
- Attempts: `1`
- Generated files: `7`
- Compile: `True`
- Pytest: `True`
- Acceptance: `True`
- Tokens: `7117`
- Estimated cost: `$0.001495`
- Budget exceeded: `False`

## Files
- `README.md`
- `data/sample_policy.txt`
- `esign_workflow.py`
- `largestack_app.py`
- `policies/approval_policy.json`
- `tests/test_esign_workflow.py`
- `tests/test_largestack_features.py`

## Validation Output
```text
evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_audit_trail_exists
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_full_workflow
  /home/questuser/Pictures/trash/agentic ai framework/largestack-agentic-ai-1.0.0-RECHECK-FIXED/release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/esign_workflow.py:23: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    'timestamp': datetime.utcnow().isoformat(),

release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_add_signer
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_send_decision_returns_executed_false
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_audit_trail_exists
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_full_workflow
  /home/questuser/Pictures/trash/agentic ai framework/largestack-agentic-ai-1.0.0-RECHECK-FIXED/release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/esign_workflow.py:38: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    'timestamp': datetime.utcnow().isoformat(),

release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_send_decision_returns_executed_false
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_audit_trail_exists
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/tests/test_esign_workflow.py::test_full_workflow
  /home/questuser/Pictures/trash/agentic ai framework/largestack-agentic-ai-1.0.0-RECHECK-FIXED/release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/23_esign_document_approval_workflow/esign_workflow.py:52: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    'timestamp': datetime.utcnow().isoformat(),

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
6 passed, 17 warnings in 4.24s

```

## Acceptance Output
```text

```

## Attempts
- round 1: mode=generate json=True checks=[] trace=537b8ffa-3134-46ac-9bff-98604b87de62