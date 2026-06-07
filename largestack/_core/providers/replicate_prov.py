"""Replicate provider — model deployment platform."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "meta/llama-2-70b-chat": {"context": 4096},
    "meta/meta-llama-3.1-405b-instruct": {"context": 128000, "tool_use": True},
    "meta/meta-llama-3-70b-instruct": {"context": 8192, "tool_use": True},
    "mistralai/mixtral-8x7b-instruct-v0.1": {"context": 32768},
    "deepseek-ai/deepseek-r1": {"context": 32768, "reasoning": True},
}


class ReplicateProvider(OpenAIProvider):
    name = "replicate"
    default_model = "meta/meta-llama-3-70b-instruct"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://openai-proxy.replicate.com/v1")

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 8192})
