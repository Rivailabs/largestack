# B2B Enterprise Knowledge Support Copilot

A B2B enterprise knowledge support copilot that answers questions using citation-backed retrieval from articles added at runtime, with insufficient evidence fallback and escalation for security/payment requests. Includes a LARGESTACK integration with guardrails PII redaction and observability tracing, all with no network side effects.

## Files

- `support_copilot.py` - Core logic: `add_article`, `answer_question`, `escalation_decision`
- `largestack_app.py` - LARGESTACK integration with `run_largestack_smoke()`
- `policies/escalation_rules.json` - Escalation policy rules
- `data/sample_article.md` - Sample article fixture
- `tests/test_support_copilot.py` - Tests for core logic
- `tests/test_largestack_features.py` - Tests for LARGESTACK features

## How to Run

```bash
# Install dependencies (largestack required for LARGESTACK features)
pip install largestack

# Run tests
pytest tests/
```

## Usage

```python
from support_copilot import add_article, answer_question, escalation_decision

add_article('sso.md', 'SAML SSO setup requires metadata upload and admin approval.')
ans = answer_question('how setup saml sso metadata?')
print(ans['answer'])  # 'SAML SSO setup requires metadata upload and admin approval.'
print(ans['citations'])  # ['sso.md']

ans = answer_question('billing tax id?')
print(ans['answer'])  # 'Insufficient evidence'

esc = escalation_decision('delete all data now')
print(esc)  # {'approval_required': True, 'reason': 'Security action requires approval', 'executed': False}
```

## LARGESTACK Integration

```python
import asyncio
from largestack_app import run_largestack_smoke

result = asyncio.run(run_largestack_smoke())
print(result)
```
