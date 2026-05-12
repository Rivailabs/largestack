# LARGESTACK_GUARDRAIL — Guardrail Blocked

**Error:** `GuardrailBlockedError`

**When:** Input or output was blocked by a guardrail (PII, injection, hallucination, toxicity, or topic).

**Solutions:**

1. **Change action to warn:** `create_guardrails(pii_action="warn")` — logs instead of blocking
2. **Disable specific guard:** `Agent(guardrails=["injection"])` — only injection, no PII
3. **Adjust sensitivity:** `InjectionGuard(sensitivity="low")` — fewer false positives
4. **Check the details:** Error message includes which guard triggered and why
