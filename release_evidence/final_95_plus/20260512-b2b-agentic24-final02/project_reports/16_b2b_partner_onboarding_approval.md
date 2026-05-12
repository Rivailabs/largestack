# b2b_partner_onboarding_approval

- Status: `PASS`
- Attempts: `2`
- Generated files: `7`
- Compile: `True`
- Pytest: `True`
- Acceptance: `True`
- Tokens: `12319`
- Estimated cost: `$0.002587`
- Budget exceeded: `False`

## Files
- `README.md`
- `data/partners_fixture.json`
- `largestack_app.py`
- `partner_onboarding.py`
- `policies/compliance_rules.json`
- `tests/test_largestack_features.py`
- `tests/test_partner_onboarding.py`

## Validation Output
```text
compile ok largestack_app.py
compile ok partner_onboarding.py
compile ok tests/test_largestack_features.py
compile ok tests/test_partner_onboarding.py
....                                                                     [100%]
4 passed in 3.59s

```

## Acceptance Output
```text
HybridRetriever: No embeddings set — using BM25-only. Call set_embeddings() for dense+BM25 hybrid search.

```

## Attempts
- round 1: mode=generate json=True checks=['pytest', 'acceptance'] trace=7b0d9c44-3337-4c78-9ede-3a460e20273b
- round 2: mode=patch json=True checks=[] trace=a3ad977d-ff3d-4028-a4fe-149c6b37304c