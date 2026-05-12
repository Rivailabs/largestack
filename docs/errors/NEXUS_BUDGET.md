# LARGESTACK_BUDGET — Budget Exceeded

**Error:** `BudgetExceededError`

**When:** Agent run cost exceeded the configured `cost_budget`.

**Example:**
```
Cost $5.0142 exceeded budget $5.00
  Suggestion: Increase budget: cost_budget=10.00
```

**Solutions:**

1. **Increase budget:** `Agent(cost_budget=10.0)`
2. **Use cheaper model:** Switch from `gpt-4o` ($10/M output) to `deepseek-chat` ($0.28/M output)
3. **Reduce max turns:** `Agent(max_turns=10)` — fewer iterations = lower cost
4. **Enable semantic cache:** Set `semantic_cache: true` in `largestack.yaml` — cached responses cost $0
5. **Pre-check cost:** `tracker.predict("gpt-4o-mini", input_tokens=5000)` returns low/expected/high estimate
