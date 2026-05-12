"""Anyscale Endpoints provider — Ray-based inference."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "meta-llama/Meta-Llama-3-70B-Instruct": {"context": 8192, "tool_use": True},
    "meta-llama/Meta-Llama-3-8B-Instruct": {"context": 8192, "tool_use": True},
    "mistralai/Mixtral-8x22B-Instruct-v0.1": {"context": 65536, "tool_use": True},
}

class AnyscaleProvider(OpenAIProvider):
    name = "anyscale"
    default_model = "meta-llama/Meta-Llama-3-70B-Instruct"
    supported_models = list(MODELS.keys())
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.endpoints.anyscale.com/v1")
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 8192})
