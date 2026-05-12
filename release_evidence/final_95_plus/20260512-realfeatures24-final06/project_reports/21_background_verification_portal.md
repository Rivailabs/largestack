# background_verification_portal

- Status: `PASS`
- Attempts: `2`
- Generated files: `7`
- Compile: `True`
- Pytest: `True`
- Acceptance: `True`
- Tokens: `10998`
- Estimated cost: `$0.00231`
- Budget exceeded: `False`

## Files
- `README.md`
- `bgv_portal.py`
- `data/policy_documents.txt`
- `largestack_app.py`
- `policies/approval_policy.txt`
- `tests/test_bgv_portal.py`
- `tests/test_largestack_features.py`

## Validation Output
```text
compile ok bgv_portal.py
compile ok largestack_app.py
compile ok tests/test_bgv_portal.py
compile ok tests/test_largestack_features.py
.........                                                                [100%]
=============================== warnings summary ===============================
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_submit_candidate_with_consent
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_verify_document_valid
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_verify_document_invalid
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_case_status_in_progress
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_case_status_verified
release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/tests/test_bgv_portal.py::test_public_contract
  /home/questuser/Pictures/trash/agentic ai framework/largestack-agentic-ai-1.0.0-RECHECK-FIXED/release_evidence/final_95_plus/20260512-realfeatures24-final06/projects/21_background_verification_portal/bgv_portal.py:17: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    'submitted_at': datetime.utcnow().isoformat()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
9 passed, 6 warnings in 3.96s

```

## Acceptance Output
```text
HybridRetriever: No embeddings set — using BM25-only. Call set_embeddings() for dense+BM25 hybrid search.

```

## Attempts
- round 1: mode=generate json=True checks=['pytest', 'acceptance'] trace=e908e214-b750-4b92-857a-31c6e46024f0
- round 2: mode=patch json=True checks=[] trace=8f420b69-ac1e-4225-b4a4-3442eac3b5fc