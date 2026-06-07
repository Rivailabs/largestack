"""Lepton AI provider — fast open model serving."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "llama3-1-8b": {"context": 128000},
    "llama3-1-70b": {"context": 128000},
    "llama3-1-405b": {"context": 128000},
    "mixtral-8x7b": {"context": 32768},
    "mistral-7b": {"context": 32768},
    "dolphin-mixtral-8x7b": {"context": 32768},
}


class LeptonProvider(OpenAIProvider):
    name = "lepton"
    default_model = "llama3-1-70b"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.lepton.ai/v1")

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 32768})
