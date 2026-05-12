# LARGESTACK_PROVIDER_AUTH — Authentication Failed

**Error:** `ProviderAuthError`  
**Retryable:** No

**When:** The API key for a provider is invalid, expired, or missing.

**Example:**
```
openai API key invalid
  Suggestion: Set: export LARGESTACK_OPENAI_API_KEY=<openai-api-key>
```

**Solutions:**

1. **Check the key is set:**
   ```bash
   echo $LARGESTACK_OPENAI_API_KEY    # Should print a non-empty key value
   largestack doctor                   # Shows which keys are configured
   ```
2. **Verify key validity:** Go to the provider's dashboard and check the key isn't revoked
3. **Check env var prefix:** LARGESTACK uses `LARGESTACK_` prefix — set `LARGESTACK_OPENAI_API_KEY`, not `OPENAI_API_KEY`
4. **Use .env file:** Create `.env` in project root with `LARGESTACK_OPENAI_API_KEY=<openai-api-key>`
