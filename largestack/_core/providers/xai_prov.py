"""xAI provider — Grok models."""

from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "grok-2-1212": {"context": 131072, "max_output": 131072, "tool_use": True, "vision": False},
    "grok-2-vision-1212": {"context": 32768, "max_output": 32768, "tool_use": True, "vision": True},
    "grok-beta": {"context": 131072, "max_output": 131072, "tool_use": True},
    "grok-vision-beta": {"context": 8192, "max_output": 8192, "tool_use": False, "vision": True},
    "grok-3": {"context": 131072, "max_output": 131072, "tool_use": True, "reasoning": True},
}


class XAIProvider(OpenAIProvider):
    name = "xai"
    default_model = "grok-2-1212"
    supported_models = list(MODELS.keys())

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.x.ai/v1")

    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 131072, "max_output": 131072})

    def validate_model(self, model: str) -> bool:
        return model.split("/")[-1] in MODELS or "grok" in model.lower()
