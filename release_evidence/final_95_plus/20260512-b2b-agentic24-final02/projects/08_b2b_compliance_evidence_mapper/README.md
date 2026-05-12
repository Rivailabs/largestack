# b2b_compliance_evidence_mapper

A B2B compliance evidence mapper that maps controls to evidence files by keywords, identifies missing evidence, and produces remediation actions with owners.

## Run

```bash
python -c "from compliance_mapper import map_control_to_evidence, gap_report; controls=[{'id':'AC-1','text':'Access reviews must be quarterly'},{'id':'IR-1','text':'Incident response tabletop annually'}]; evidence={'access_review_q1.pdf':'Quarterly access review completed','backup.txt':'Backups tested'}; mapping=map_control_to_evidence(controls, evidence); print(mapping); gap=gap_report(mapping); print(gap)"
```

## Test

```bash
pip install pytest
pytest tests/
```

## LARGESTACK Smoke Test

```bash
python -c "import asyncio; from largestack_app import run_largestack_smoke; print(asyncio.run(run_largestack_smoke()))"
```
