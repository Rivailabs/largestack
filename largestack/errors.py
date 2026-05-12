"""Self-documenting error hierarchy. Every error has error_code, suggestion, docs_url."""

class LargestackError(Exception):
    retryable = False
    error_code = "LARGESTACK_UNKNOWN"
    docs_url = "https://largestack-ai.dev/errors/"
    def __init__(self, message: str, suggestion: str = ""):
        self.suggestion = suggestion
        super().__init__(message)
    def __str__(self):
        parts = [super().__str__()]
        if self.suggestion: parts.append(f"  Suggestion: {self.suggestion}")
        parts.append(f"  Docs: {self.docs_url}{self.error_code}")
        return "\n".join(parts)

class ProviderError(LargestackError):
    error_code = "LARGESTACK_PROVIDER"

class ProviderTimeoutError(ProviderError):
    retryable = True; error_code = "LARGESTACK_PROVIDER_TIMEOUT"
    def __init__(self, provider: str, timeout: float):
        super().__init__(f"{provider} timed out after {timeout}s", f"Increase timeout or add fallback provider")

class ProviderAuthError(ProviderError):
    error_code = "LARGESTACK_PROVIDER_AUTH"
    def __init__(self, provider: str):
        super().__init__(f"{provider} API key invalid", f"Set: export LARGESTACK_{provider.upper()}_API_KEY=...")

class ProviderRateLimitError(ProviderError):
    retryable = True; error_code = "LARGESTACK_RATE_LIMIT"

class AllProvidersFailedError(ProviderError):
    error_code = "LARGESTACK_ALL_FAILED"
    def __init__(self, tried: list[str]):
        super().__init__(f"All providers failed: {', '.join(tried)}", "Add local fallback: llm='ollama/llama3'")

class BudgetExceededError(LargestackError):
    error_code = "LARGESTACK_BUDGET"
    def __init__(self, actual: float, budget: float):
        super().__init__(f"Cost ${actual:.4f} exceeded budget ${budget:.2f}", f"Increase: cost_budget={budget*2:.2f}")

class LoopDetectedError(LargestackError):
    error_code = "LARGESTACK_LOOP"
    def __init__(self, iters: int, reason: str = ""):
        super().__init__(f"Agent stuck after {iters} iterations ({reason})", "Improve instructions or reduce max_turns")

class ContextWindowExceededError(LargestackError):
    error_code = "LARGESTACK_CONTEXT"
    def __init__(self, sent: int, maximum: int, model: str):
        super().__init__(f"{sent} tokens > {model} max {maximum}", "Use larger model or enable compression")

class LicenseRequiredError(LargestackError):
    error_code = "LARGESTACK_LICENSE"
    def __init__(self):
        super().__init__("Production requires license", "Get one at https://largestack-ai.dev/pricing ($299/yr)")

class GuardrailBlockedError(LargestackError):
    error_code = "LARGESTACK_GUARDRAIL"
    def __init__(self, guard_type: str, details: str):
        super().__init__(f"Blocked by {guard_type}: {details}", "Adjust config or set action='warn'")

class KillSwitchActivatedError(LargestackError):
    error_code = "LARGESTACK_KILL_SWITCH"
    def __init__(self, by: str = "operator"):
        super().__init__(f"Kill switch by {by}", "Resume: largestack resume")

class ToolExecutionError(LargestackError):
    error_code = "LARGESTACK_TOOL"
    def __init__(self, tool: str, error: str):
        super().__init__(f"Tool '{tool}' failed: {error}", "Check tool config and permissions")

class ToolPermissionError(LargestackError):
    error_code = "LARGESTACK_TOOL_PERM"
    def __init__(self, tool: str, agent: str):
        super().__init__(f"Agent '{agent}' cannot use tool '{tool}'", f"Add '{tool}' to allow list")

class ModelRequestsBlockedError(LargestackError):
    """Raised when a real provider call is attempted while ALLOW_MODEL_REQUESTS=False.

    Use the test override pattern instead:
        with agent.override(model=TestModel()):
            await agent.run(...)
    Or wrap test code in `with block_model_requests():` to assert no real calls happen.
    """
    error_code = "LARGESTACK_MODEL_BLOCKED"
    def __init__(self, model: str = ""):
        super().__init__(
            f"Real model request blocked (model={model!r}). "
            f"ALLOW_MODEL_REQUESTS is False.",
            "Use agent.override(model=TestModel(...)) inside the block, "
            "or call enable_model_requests() to re-enable.",
        )
