"""Cloudflare Workers AI provider — serverless model inference."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": {"context": 24000, "tool_use": True},
    "@cf/meta/llama-3.1-70b-instruct": {"context": 7500, "tool_use": True},
    "@cf/meta/llama-3.1-8b-instruct-fast": {"context": 128000, "tool_use": True},
    "@cf/mistral/mistral-7b-instruct-v0.1": {"context": 32768},
    "@cf/qwen/qwen1.5-14b-chat-awq": {"context": 7500},
    "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b": {"context": 80000, "reasoning": True},
}

class CloudflareAIProvider(OpenAIProvider):
    name = "cloudflare"
    default_model = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    supported_models = list(MODELS.keys())
    def __init__(self, api_key: str, account_id: str = ""):
        # Cloudflare Workers AI uses account-specific endpoints
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1" if account_id else "https://api.cloudflare.com/client/v4/ai/v1"
        super().__init__(api_key=api_key, base_url=url)
        self.account_id = account_id
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 7500})
