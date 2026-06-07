"""Hierarchical config: defaults → env (LARGESTACK_*) → yaml → code."""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class LargestackConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LARGESTACK_", env_file=".env", extra="ignore")

    # Runtime environment
    env: str = "development"

    # Agent defaults
    default_llm: str = "openai/gpt-4o-mini"
    max_turns: int = 25
    cost_budget: float = 5.0

    # LLM provider keys (13 providers)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    # Generic OpenAI-compatible endpoint (local/vLLM/LM Studio/custom gateway).
    # Use model string: local/<model-name> or openai_compatible/<model-name>.
    openai_compatible_api_key: str = "local"
    openai_compatible_base_url: str = ""
    # Register Ollama's OpenAI-compatible /v1 endpoint as local/<model>.
    # This path can support tool-calling when the selected local model/runtime supports it.
    ollama_openai_compat: bool = False
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    together_api_key: str = ""
    fireworks_api_key: str = ""
    cohere_api_key: str = ""
    bedrock_region: str = ""  # Empty default — set explicitly to enable Bedrock
    azure_openai_key: str = ""
    azure_openai_endpoint: str = ""
    ollama_base_url: str = "http://localhost:11434"
    # Additional providers
    perplexity_api_key: str = ""
    cerebras_api_key: str = ""
    sambanova_api_key: str = ""
    openrouter_api_key: str = ""
    xai_api_key: str = ""
    ai21_api_key: str = ""
    lepton_api_key: str = ""
    nvidia_api_key: str = ""

    # Observability export
    trace_backend: str = "sqlite"  # sqlite, langfuse, otlp, jaeger, console
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    otlp_endpoint: str = "http://localhost:4317"

    # Observability
    trace_enabled: bool = True
    trace_db_path: str = "~/.largestack/traces.db"
    metrics_enabled: bool = True

    # Guardrails
    guardrails_enabled: bool = True
    pii_detection: bool = True
    injection_detection: bool = True
    hallucination_detection: bool = False
    toxicity_detection: bool = False
    topic_blocklist: str = ""  # Comma-separated

    # License
    license_key: str = ""

    # Dashboard
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8787

    # Kill switch
    kill_switch_backend: str = "file"  # file or redis
    redis_url: str = "redis://localhost:6379"

    # Feature flags
    smart_routing: bool = False
    semantic_cache: bool = True
    context_compression: bool = False

    @classmethod
    def load(cls, path: Optional[str] = None, **kw) -> "LargestackConfig":
        yd = {}
        for p in [
            path,
            "largestack.yaml",
            "largestack.yml",
            os.path.expanduser("~/.largestack/config.yaml"),
        ]:
            if p and Path(p).exists():
                with open(p) as f:
                    yd = yaml.safe_load(f) or {}
                break
        return cls(**{**yd, **kw})


_cfg: Optional[LargestackConfig] = None


def get_config(**kw) -> LargestackConfig:
    global _cfg
    if _cfg is None or kw:
        _cfg = LargestackConfig.load(**kw)
    return _cfg
