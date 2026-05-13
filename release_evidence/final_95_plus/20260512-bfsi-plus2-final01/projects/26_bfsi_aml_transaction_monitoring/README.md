# BFSI AML Transaction Monitoring

Local LARGESTACK BFSI validation artifact for AML alert screening.

## Features

- Deterministic AML screening for sanctions, volume spikes, high-risk keywords, and KYC risk.
- Local SAR draft preparation with maker/checker style review flags; no external filing.
- Citation-backed AML policy answers with insufficient-evidence behavior.
- Real LARGESTACK smoke using router orchestration, RAG citations, and observability capture under `TestModel`.

## Test

```bash
python -m pytest tests -q
```
