# Largestack AI — Troubleshooting

## Common Issues

### "All providers failed"
**Error:** `AllProvidersFailedError`

**Cause:** No API key configured for any provider, or all providers are rate-limited/down.

**Fix:**
1. Run `largestack doctor` to check which keys are set.
2. Set at least one: `export LARGESTACK_OPENAI_API_KEY=<openai-api-key>`
3. Add a local fallback: `llm="ollama/llama3"` (requires Ollama running).
4. Check provider status pages.

### "Budget exceeded"
**Error:** `BudgetExceededError`

**Cause:** Agent run cost exceeded `cost_budget`.

**Fix:** Increase budget: `Agent(cost_budget=10.0)` or use cheaper model: `llm="deepseek/deepseek-chat"`.

### "Agent stuck in loop"
**Error:** `LoopDetectedError`

**Cause:** One of 5 loop detectors triggered (max turns, cost, repeated actions, no progress, timeout).

**Fix:**
1. Improve agent instructions to be more specific.
2. Increase `max_turns` if the task genuinely needs more iterations.
3. Check if tool responses are useful (bad tool output → agent retries forever).

### "Kill switch activated"
**Error:** `KillSwitchActivatedError`

**Cause:** Someone activated the emergency kill switch.

**Fix:** Run `largestack resume` to deactivate.

### "Tool permission denied"
**Error:** `ToolPermissionError`

**Cause:** Agent tried to use a tool not in its `allow` list.

**Fix:** Add tool to permissions: `Agent(tool_permissions={"allow": ["web_search", "calculator"]})`.

### PII detected in output
**Warning:** Guardrail triggered PII detection.

**Fix:** This is working as intended. To change behavior: `create_guardrails(pii_action="block")` or `"redact"` or `"warn"`.

### "Presidio/spaCy not installed"
**Warning:** Enhanced PII detection falls back to regex.

**Fix:** `pip install presidio-analyzer presidio-anonymizer && python -m spacy download en_core_web_sm`

### Slow first request
**Cause:** Model loading, connection establishment, tracing setup.

**Fix:** This is normal for first request. Subsequent requests use connection pooling and caching.

### Dashboard shows no data
**Cause:** Tracing or audit trail not populated.

**Fix:** Run an agent first: `python examples/01_hello/main.py`. Dashboard reads from `~/.largestack/traces.db` and `~/.largestack/audit.db`.

## Diagnostic Commands

```bash
largestack doctor        # Check Python, API keys, Ollama, dependencies
largestack trace         # View recent traces
largestack cost          # View cost breakdown per agent
```
