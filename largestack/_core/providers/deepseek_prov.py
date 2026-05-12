"""DeepSeek provider — OpenAI-compatible API, cheapest model ($0.14/$0.28 per 1M)."""
from __future__ import annotations
from largestack._core.providers.openai_prov import OpenAIProvider

class DeepSeekProvider(OpenAIProvider):
    """DeepSeek uses OpenAI-compatible API format."""
    name = "deepseek"
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.deepseek.com/v1")
    
    def count_tokens(self, text: str, model: str) -> int:
        return len(text) // 4  # No tiktoken for DeepSeek
