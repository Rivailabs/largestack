"""Fireworks AI provider — fast open source model inference."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "accounts/fireworks/models/llama-v3p3-70b-instruct": {"context": 131072, "tool_use": True},
    "accounts/fireworks/models/llama-v3p1-405b-instruct": {"context": 131072, "tool_use": True},
    "accounts/fireworks/models/deepseek-v3": {"context": 131072, "tool_use": True},
    "accounts/fireworks/models/deepseek-r1": {"context": 160000, "reasoning": True},
    "accounts/fireworks/models/qwen2p5-72b-instruct": {"context": 32768, "tool_use": True},
    "accounts/fireworks/models/mixtral-8x22b-instruct": {"context": 65536, "tool_use": True},
}

class FireworksProvider(OpenAIProvider):
    name = "fireworks"
    default_model = "accounts/fireworks/models/llama-v3p3-70b-instruct"
    supported_models = list(MODELS.keys())
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.fireworks.ai/inference/v1")
    
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 32768})
