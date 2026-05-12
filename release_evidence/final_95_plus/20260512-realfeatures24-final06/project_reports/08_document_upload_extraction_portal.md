# document_upload_extraction_portal

- Status: `PASS`
- Attempts: `2`
- Generated files: `7`
- Compile: `True`
- Pytest: `True`
- Acceptance: `True`
- Tokens: `10761`
- Estimated cost: `$0.00226`
- Budget exceeded: `False`

## Files
- `README.md`
- `data/sample_invoice.txt`
- `document_portal.py`
- `largestack_app.py`
- `policies/upload_policy.json`
- `tests/test_document_portal.py`
- `tests/test_largestack_features.py`

## Validation Output
```text
compile ok document_portal.py
compile ok largestack_app.py
compile ok tests/test_document_portal.py
compile ok tests/test_largestack_features.py
...........                                                              [100%]
11 passed in 3.85s

```

## Acceptance Output
```text
HybridRetriever: No embeddings set — using BM25-only. Call set_embeddings() for dense+BM25 hybrid search.

```

## Attempts
- round 1: mode=generate json=True checks=['pytest', 'acceptance'] trace=1b1046aa-ddfc-4385-add2-b0b48b5db7bd
- round 2: mode=patch json=True checks=[] trace=c857a0f2-b0ae-4b60-87b8-be56d6fe476b