"""SambaNova provider — Llama inference on custom silicon."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "Meta-Llama-3.3-70B-Instruct": {"context": 131072, "speed": "460 tokens/sec"},
    "Meta-Llama-3.1-405B-Instruct": {"context": 16384, "speed": "132 tokens/sec"},
    "Meta-Llama-3.1-70B-Instruct": {"context": 131072, "speed": "450 tokens/sec"},
    "Meta-Llama-3.1-8B-Instruct": {"context": 16384, "speed": "1050 tokens/sec"},
    "Qwen2.5-72B-Instruct": {"context": 131072, "tool_use": True},
}


class SambaNovaProvider(OpenAIProvider):
    name = "sambanova"
    default_model = "Meta-Llama-3.3-70B-Instruct"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.sambanova.ai/v1")

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 16384})
