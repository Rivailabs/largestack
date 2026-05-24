# LARGESTACK_UNKNOWN — Unexpected Error

**Error:** `LargestackError` (base class)  
**Retryable:** Varies

**When:** An error occurred that doesn't match a specific error type. This is the catch-all.

**Solutions:**

1. **Check the error message** — it usually describes what went wrong
2. **Check the suggestion** — every LargestackError includes a `.suggestion` field
3. **Enable debug logging:** `LARGESTACK_LOG_LEVEL=DEBUG python agent.py`
4. **File a bug:** If this is unexpected, report it through the public issue tracker once the GitHub repository is visible.
