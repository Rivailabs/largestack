"""Mistral provider (OpenAI-compatible)."""

from largestack._core.providers.openai_prov import OpenAIProvider


class MistralProvider(OpenAIProvider):
    name = "mistral"

    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.mistral.ai/v1")

    def count_tokens(self, text, model):
        return len(text) // 4
