# bfsi_aml_transaction_monitoring

- Status: `PASS`
- Attempts: `1`
- Generated files: `9`
- Compile: `True`
- Pytest: `True`
- Acceptance: `True`
- Tokens: `8829`
- Estimated cost: `$0.001854`
- Budget exceeded: `False`

## Files
- `README.md`
- `aml_monitoring.py`
- `data/customers.csv`
- `data/transactions.csv`
- `data/watchlist.json`
- `largestack_app.py`
- `policies/aml_policy.md`
- `tests/test_aml_monitoring.py`
- `tests/test_largestack_features.py`

## Validation Output
```text
compile ok aml_monitoring.py
compile ok largestack_app.py
compile ok tests/test_aml_monitoring.py
compile ok tests/test_largestack_features.py
...........                                                              [100%]
11 passed in 1.39s

```

## Acceptance Output
```text
HybridRetriever: No embeddings set — using BM25-only. Call set_embeddings() for dense+BM25 hybrid search.

```

## Attempts
- round 1: mode=generate json=True checks=[] trace=cb5717c1-9376-4e89-b609-8c9c76b14c83