"""Together AI provider — 200+ open source models."""
from largestack._core.providers.openai_prov import OpenAIProvider

MODELS = {
    "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": {"context": 130815, "tool_use": True},
    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": {"context": 130815, "tool_use": True},
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": {"context": 130815, "tool_use": True},
    "meta-llama/Llama-3.3-70B-Instruct-Turbo": {"context": 130815, "tool_use": True},
    "mistralai/Mistral-7B-Instruct-v0.3": {"context": 32768, "tool_use": True},
    "mistralai/Mixtral-8x7B-Instruct-v0.1": {"context": 32768, "tool_use": True},
    "Qwen/Qwen2.5-72B-Instruct-Turbo": {"context": 32768, "tool_use": True},
    "Qwen/QwQ-32B-Preview": {"context": 32768, "reasoning": True},
    "deepseek-ai/DeepSeek-V3": {"context": 131072, "tool_use": True},
    "deepseek-ai/DeepSeek-R1": {"context": 131072, "reasoning": True},
}

class TogetherProvider(OpenAIProvider):
    name = "together"
    default_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    supported_models = list(MODELS.keys())
    
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key, base_url="https://api.together.xyz/v1")
    
    def count_tokens(self, text, model): return len(text) // 4
    
    def get_capabilities(self, model: str) -> dict:
        for k, v in MODELS.items():
            if k in model: return v
        return {"context": 32768, "max_output": 4096}
