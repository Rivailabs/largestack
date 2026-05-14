# Testing and Validation

Largestack uses layered validation. The goal is not only to check that code imports, but that agents, tools, RAG, guardrails, security, packaging, Docker, and live provider paths work together.

---

## Test layers

| Layer | Command | Purpose |
|---|---|---|
| Compile | `python -m compileall largestack tests examples scripts` | Syntax/import sanity |
| Unit | `python -m pytest tests/unit -q --tb=short -ra` | Core components |
| Security | `python -m pytest tests/security -q --tb=short -ra` | Security behavior |
| RAG eval | `python -m pytest tests/rag_eval -q --tb=short -ra` | Retrieval/citation behavior |
| Integration | `python -m pytest tests/integration -q --tb=short -ra` | Cross-module/provider paths |
| Full suite | `python -m pytest tests -q --tb=short -ra` | Main validation gate |
| Build | `python -m build && twine check dist/*` | Package integrity |
| Security scan | `gitleaks`, `bandit`, `pip-audit` | Release security gate |
| Docker | `docker build` + `/health` | Runtime container proof |
| Helm | `helm lint` + `helm template` | K8s manifest sanity |
| Soak | 4h/24h loop | Long-running stability |

---

## Confirmed RC evidence

The project has recorded evidence for:

- Ubuntu full validation,
- Mac validation,
- Windows clean validation,
- DeepSeek live difficult-project validation,
- RAG/security/integration tests,
- Docker runtime health,
- Helm lint/template,
- 4-hour soak evidence,
- 24-hour soak completed with 210 successful cycles and no recorded test failures.

---

## 24-hour soak test

A soak test proves that a system keeps working for hours, not only once.

Basic soak command:

```bash
cd /home/questuser/Projects/largestack-ubuntu-clean
source .venv/bin/activate
mkdir -p release_evidence/soak_24h

nohup bash -c '
START=$(date)
END=$((SECONDS+86400))

echo "# Largestack 24h Soak Test" > release_evidence/soak_24h/soak_24h.log
echo "Started: $START" >> release_evidence/soak_24h/soak_24h.log

while [ $SECONDS -lt $END ]; do
  date >> release_evidence/soak_24h/soak_24h.log
  python -m pytest \
    tests/unit/test_memory.py \
    tests/unit/test_workflow.py \
    tests/unit/test_rag.py \
    tests/security/test_injection_attacks.py \
    tests/security/test_xss_dashboard.py \
    -q --tb=short >> release_evidence/soak_24h/soak_24h.log 2>&1
  echo "----" >> release_evidence/soak_24h/soak_24h.log
  sleep 300
done

echo "Completed: $(date)" >> release_evidence/soak_24h/soak_24h.log
' > release_evidence/soak_24h/nohup.out 2>&1 &
```

Check status:

```bash
ps aux | grep soak_24h | grep -v grep
tail -n 80 release_evidence/soak_24h/soak_24h.log
```

Strict rule: if the machine sleeps/shuts down, the soak is not continuous. Restart from zero for public SaaS proof.

---

## Release sign-off checklist

| Gate | Required before public release? |
|---|---|
| Full pytest pass | Yes |
| Mac validation | Yes |
| Windows validation | Yes |
| Docker health | Yes |
| Build/twine | Yes |
| Secret scan | Yes |
| Bandit medium/high clean | Yes |
| pip-audit clean or documented | Yes |
| 24h soak | Yes |
| Real K8s install | Yes for enterprise/K8s claim |
| External VAPT | Yes for regulated enterprise |
