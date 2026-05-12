"""OpenRouter provider — unified gateway to 300+ models with fallback."""
from largestack._core.providers.openai_prov import OpenAIProvider

# Just the top ones — full list at openrouter.ai/models
POPULAR_MODELS = {
    "anthropic/claude-3.5-sonnet": {"context": 200000, "tool_use": True, "vision": True},
    "anthropic/claude-3.5-haiku": {"context": 200000, "tool_use": True},
    "openai/gpt-4o": {"context": 128000, "tool_use": True, "vision": True},
    "openai/gpt-4o-mini": {"context": 128000, "tool_use": True, "vision": True},
    "google/gemini-2.0-flash-exp": {"context": 1000000, "tool_use": True, "vision": True},
    "meta-llama/llama-3.3-70b-instruct": {"context": 128000, "tool_use": True},
    "deepseek/deepseek-chat": {"context": 64000, "tool_use": True},
    "deepseek/deepseek-r1": {"context": 128000, "reasoning": True},
    "qwen/qwen-2.5-72b-instruct": {"context": 131072, "tool_use": True},
}

class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"
    default_model = "anthropic/claude-3.5-sonnet"
    supported_models = list(POPULAR_MODELS.keys())
    
    def __init__(self, api_key: str, site_url: str = None, app_name: str = None):
        super().__init__(api_key=api_key, base_url="https://openrouter.ai/api/v1")
        # OpenRouter-specific headers for analytics
        self.extra_headers = {}
        if site_url: self.extra_headers["HTTP-Referer"] = site_url
        if app_name: self.extra_headers["X-Title"] = app_name
    
    def get_capabilities(self, model: str) -> dict:
        return POPULAR_MODELS.get(model, {"context": 32768})
