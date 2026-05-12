# LARGESTACK_ALL_FAILED — All Providers Failed

**Error:** `AllProvidersFailedError`  
**Retryable:** No

**When:** Every provider in the fallback chain failed (auth error, rate limit, timeout, or circuit breaker open).

**Example:**
```
All providers failed: openai, anthropic, ollama
  Suggestion: Check provider status pages or add a local fallback: llm=ollama/llama3
```

**Solutions:**

1. **Run `largestack doctor`** — shows which providers are configured and reachable
2. **Add local fallback:** Install Ollama (`curl -fsSL https://ollama.com/install.sh | sh`) and pull a model (`ollama pull llama3`)
3. **Check circuit breakers:** If a provider had 5+ consecutive failures, its circuit breaker is OPEN. It auto-resets after 30 seconds
4. **Check provider status:** Visit status.openai.com, status.anthropic.com, etc.
5. **Configure more providers:** Each additional API key adds a fallback option
