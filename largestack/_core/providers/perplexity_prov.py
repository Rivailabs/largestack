"""Perplexity provider — Sonar models with online search capability."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "sonar": {"context": 127000, "max_output": 4096, "online": True, "citations": True},
    "sonar-pro": {"context": 200000, "max_output": 8192, "online": True, "citations": True},
    "sonar-reasoning": {"context": 127000, "max_output": 8192, "online": True, "reasoning": True},
    "sonar-reasoning-pro": {"context": 127000, "max_output": 8192, "online": True, "reasoning": True, "citations": True},
    "sonar-deep-research": {"context": 127000, "max_output": 8192, "online": True, "deep_research": True},
}

class PerplexityProvider(OpenAIProvider):
    name = "perplexity"
    default_model = "sonar"
    supported_models = list(MODELS.keys())
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.perplexity.ai")
    
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 127000, "max_output": 4096})
    
    def validate_model(self, model: str) -> bool:
        m = model.split("/")[-1]
        return m in MODELS or m.startswith("sonar")
