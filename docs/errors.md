# Errors

Every Largestack exception subclasses `LargestackError` and carries three things:
a stable `error_code`, a human-readable `.suggestion`, and a `docs_url`. Printing the
exception renders all three.

```python
from largestack.errors import ProviderAuthError

print(ProviderAuthError("openai"))
# openai API key invalid
#   Suggestion: Set: export LARGESTACK_OPENAI_API_KEY=...
#   Docs: https://docs.largestack.ai/errors/LARGESTACK_PROVIDER_AUTH
```

| Attribute | Meaning |
|---|---|
| `error_code` | Stable code, e.g. `LARGESTACK_RATE_LIMIT` |
| `retryable` | `True` if a retry can succeed |
| `suggestion` | Actionable fix (shown in `str()`) |
| `docs_url` | Base docs URL (`error_code` is appended in `str()`) |

---

## Exception table

All importable from `largestack.errors`. (Common ones are also re-exported from the
top-level `largestack` package — see the import note below.)

| Exception | `error_code` | Retryable | Raised when | Handle by |
|---|---|---|---|---|
| `LargestackError` | `LARGESTACK_UNKNOWN` | No | Base class for all of the below | Catch-all for any framework error |
| `ProviderError` | `LARGESTACK_PROVIDER` | No | Generic provider failure (base for provider errors) | Inspect message; consider fallback |
| `ProviderTimeoutError` | `LARGESTACK_PROVIDER_TIMEOUT` | **Yes** | LLM did not respond within the timeout | Increase timeout or add a fallback provider |
| `ProviderAuthError` | `LARGESTACK_PROVIDER_AUTH` | No | API key missing/invalid | Set `LARGESTACK_<PROVIDER>_API_KEY` |
| `ProviderRateLimitError` | `LARGESTACK_RATE_LIMIT` | **Yes** | Provider returned a rate limit | Back off / retry; add fallback |
| `AllProvidersFailedError` | `LARGESTACK_ALL_FAILED` | No | Every provider in the fallback chain failed | Add a local fallback (`ollama/...`) |
| `BudgetExceededError` | `LARGESTACK_BUDGET` | No | Run cost exceeded `cost_budget` | Raise `cost_budget` or trim work |
| `LoopDetectedError` | `LARGESTACK_LOOP` | No | Agent stuck repeating itself | Improve instructions / lower `max_turns` |
| `ContextWindowExceededError` | `LARGESTACK_CONTEXT` | No | Prompt tokens exceed the model max | Use a larger model / enable compression |
| `LicenseRequiredError` | `LARGESTACK_LICENSE` | No | Production path needs a license | Activate a license |
| `GuardrailBlockedError` | `LARGESTACK_GUARDRAIL` | No | Input/output blocked by a guardrail | Adjust config or set `action="warn"` |
| `KillSwitchActivatedError` | `LARGESTACK_KILL_SWITCH` | No | Emergency kill switch is active | `largestack resume` |
| `ToolExecutionError` | `LARGESTACK_TOOL` | No | A tool function raised | Check tool config / inputs |
| `ToolPermissionError` | `LARGESTACK_TOOL_PERM` | No | Agent lacks permission for a tool | Add the tool to the allow list |
| `ModelRequestsBlockedError` | `LARGESTACK_MODEL_BLOCKED` | No | A real provider call attempted while model requests are blocked | Use `agent.override(model=TestModel(...))` or `enable_model_requests()` |

`GuardrailBlockedError` additionally exposes `.guard_type` (e.g. `"PIIGuard"`).

---

## Handling

Catch specific types, or branch on `retryable`:

```python
from largestack.errors import (
    LargestackError,
    ProviderRateLimitError,
    BudgetExceededError,
    GuardrailBlockedError,
)

try:
    ...  # await agent.run(...)
except ProviderRateLimitError as e:
    print("retryable:", e.retryable)   # True — back off and retry
except BudgetExceededError as e:
    print(e.suggestion)                 # raise cost_budget
except GuardrailBlockedError as e:
    print("blocked by", e.guard_type)
except LargestackError as e:
    print(e.error_code, "-", e.suggestion)
```

---

## Import note

These names are re-exported from the top-level package for convenience:

```python
from largestack import (
    LargestackError,
    BudgetExceededError,
    LoopDetectedError,
    ProviderError,
    GuardrailBlockedError,
    KillSwitchActivatedError,
    ToolExecutionError,
    ToolPermissionError,
    ModelRequestsBlockedError,
)
```

The remaining types (`ProviderTimeoutError`, `ProviderAuthError`,
`ProviderRateLimitError`, `AllProvidersFailedError`, `ContextWindowExceededError`,
`LicenseRequiredError`) are imported from `largestack.errors`.
