# Largestack AI — Error Reference

Every error includes an error code, suggestion, and documentation URL.

| Error | Code | Retryable | When |
|-------|------|-----------|------|
| `ProviderTimeoutError` | LARGESTACK_PROVIDER_TIMEOUT | Yes | LLM didn't respond in time |
| `ProviderAuthError` | LARGESTACK_PROVIDER_AUTH | No | Invalid API key |
| `ProviderRateLimitError` | LARGESTACK_RATE_LIMIT | Yes | Provider rate limit hit |
| `AllProvidersFailedError` | LARGESTACK_ALL_FAILED | No | Every provider in fallback chain failed |
| `BudgetExceededError` | LARGESTACK_BUDGET | No | Run cost exceeded `cost_budget` |
| `LoopDetectedError` | LARGESTACK_LOOP | No | Agent stuck (5-layer detection) |
| `ContextWindowExceededError` | LARGESTACK_CONTEXT | No | Tokens exceed model max |
| `LicenseRequiredError` | LARGESTACK_LICENSE | No | Production without license |
| `GuardrailBlockedError` | LARGESTACK_GUARDRAIL | No | Input/output blocked by guardrail |
| `KillSwitchActivatedError` | LARGESTACK_KILL_SWITCH | No | Emergency kill switch active |
| `ToolExecutionError` | LARGESTACK_TOOL | Varies | Tool function raised exception |
| `ToolPermissionError` | LARGESTACK_TOOL_PERM | No | Agent lacks permission for tool |

All errors inherit from `LargestackError` with `.suggestion` and `.help_url` properties.
