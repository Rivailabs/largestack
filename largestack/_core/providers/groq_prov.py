"""Groq provider — ultra-fast inference. Real model catalog + capabilities."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "llama-3.3-70b-versatile": {"context": 128000, "max_output": 32768, "tool_use": True},
    "llama-3.1-8b-instant": {"context": 128000, "max_output": 8192, "tool_use": True},
    "llama-3.1-70b-versatile": {"context": 128000, "max_output": 8192, "tool_use": True},
    "mixtral-8x7b-32768": {"context": 32768, "max_output": 32768, "tool_use": True},
    "gemma2-9b-it": {"context": 8192, "max_output": 8192, "tool_use": False},
    "deepseek-r1-distill-llama-70b": {"context": 128000, "max_output": 131072, "tool_use": True},
}

class GroqProvider(OpenAIProvider):
    name = "groq"
    default_model = "llama-3.3-70b-versatile"
    supported_models = list(MODELS.keys())
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    
    def count_tokens(self, text, model):
        return len(text) // 4  # Llama tokenizer approx
    
    def get_capabilities(self, model: str) -> dict:
        return MODELS.get(model.split("/")[-1], {"context": 8192, "max_output": 8192, "tool_use": False})
    
    def validate_model(self, model: str) -> bool:
        m = model.split("/")[-1]
        return m in MODELS or m.startswith(("llama", "mixtral", "gemma", "deepseek"))
