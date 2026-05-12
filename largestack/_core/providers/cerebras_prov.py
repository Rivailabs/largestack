"""Cerebras provider — world's fastest Llama inference."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "llama3.1-8b": {"context": 128000, "max_output": 8192, "speed": "2100 tokens/sec"},
    "llama3.1-70b": {"context": 128000, "max_output": 8192, "speed": "450 tokens/sec"},
    "llama-3.3-70b": {"context": 128000, "max_output": 8192, "speed": "2200 tokens/sec"},
}

class CerebrasProvider(OpenAIProvider):
    name = "cerebras"
    default_model = "llama-3.3-70b"
    supported_models = list(MODELS.keys())
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.cerebras.ai/v1")
    
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 128000})
