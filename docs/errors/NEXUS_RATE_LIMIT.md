# LARGESTACK_RATE_LIMIT — Provider Rate Limited

**Error:** `ProviderRateLimitError`  
**Retryable:** Yes (automatic)

**When:** The LLM provider returned HTTP 429 (Too Many Requests).

LARGESTACK automatically retries 3 times with exponential backoff + jitter (1s → 4s → 16s). If all retries fail, the fallback chain tries other providers.

**Solutions:**

1. **Wait — automatic retry handles most cases**
2. **Add fallback providers:** Configure multiple API keys so the fallback chain has alternatives
3. **Reduce request rate:** Lower `max_turns` or add delays between agent runs
4. **Upgrade provider tier:** Most providers have higher rate limits on paid plans
5. **Enable semantic cache:** `semantic_cache: true` — cached responses don't hit the API
