"""AI21 provider — Jamba models."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "jamba-1.5-large": {"context": 256000, "tool_use": True, "context_grounding": True},
    "jamba-1.5-mini": {"context": 256000, "tool_use": True},
    "jamba-instruct": {"context": 256000, "tool_use": False},
}


class AI21Provider(OpenAIProvider):
    name = "ai21"
    default_model = "jamba-1.5-large"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.ai21.com/studio/v1")

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 256000})
