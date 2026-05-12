"""NVIDIA NIM provider — enterprise-grade model catalog."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "meta/llama-3.3-70b-instruct": {"context": 128000, "tool_use": True},
    "meta/llama-3.1-405b-instruct": {"context": 128000, "tool_use": True},
    "meta/llama-3.1-70b-instruct": {"context": 128000, "tool_use": True},
    "nvidia/nemotron-4-340b-instruct": {"context": 4096, "tool_use": True},
    "nvidia/llama-3.1-nemotron-70b-instruct": {"context": 128000, "tool_use": True},
    "microsoft/phi-3-medium-128k-instruct": {"context": 128000},
    "mistralai/mixtral-8x22b-instruct-v0.1": {"context": 65536},
    "google/gemma-2-27b-it": {"context": 8192},
}

class NVIDIAProvider(OpenAIProvider):
    name = "nvidia"
    default_model = "meta/llama-3.3-70b-instruct"
    supported_models = list(MODELS.keys())
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://integrate.api.nvidia.com/v1")
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model, {"context": 4096})
