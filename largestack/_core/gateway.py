"""LLM Gateway — 25 providers, smart routing, semantic cache, retry, fallback."""

from __future__ import annotations
import hashlib, json, logging, os, time
from typing import Any, AsyncIterator

try:
    from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
except ImportError:  # pragma: no cover - fallback for minimal/offline installs

    def retry(*_args, **_kwargs):
        def _decorator(fn):
            return fn

        return _decorator

    def stop_after_attempt(*_args, **_kwargs):
        return None

    def wait_exponential_jitter(*_args, **_kwargs):
        return None

    def retry_if_exception_type(*_args, **_kwargs):
        return None


from largestack._core.config import LargestackConfig, get_config
from largestack._core.cost import CostTracker
from largestack._core.events import bus
from largestack._core.providers.base import BaseProvider
from largestack._core.semantic_cache import SemanticCache
from largestack._core.circuit_breaker import CircuitBreaker
from largestack.errors import AllProvidersFailedError, ProviderError
from largestack.types import LLMResponse

log = logging.getLogger("largestack.gateway")

PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "ollama": "ollama",
    "local": "local",
    "openai_compatible": "openai_compatible",
    "ollama_openai": "ollama_openai",
    "deepseek": "deepseek",
    "google": "google",
    "groq": "groq",
    "mistral": "mistral",
    "bedrock": "bedrock",
    "azure": "azure",
    "together": "together",
    "fireworks": "fireworks",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "cerebras": "cerebras",
    "sambanova": "sambanova",
    "openrouter": "openrouter",
    "xai": "xai",
    "ai21": "ai21",
    "lepton": "lepton",
    "nvidia": "nvidia",
    "anyscale": "anyscale",
    "cloudflare": "cloudflare",
    "voyage": "voyage",
    "databricks": "databricks",
    "replicate": "replicate",
    # v0.7.0: LiteLLM gateway — wraps 100+ providers under one umbrella.
    # Use as ``litellm/<provider>/<model>`` e.g. ``litellm/bedrock/anthropic.claude-3-sonnet``
    "litellm": "litellm",
}
MODEL_PREFIX_MAP = {
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude": "anthropic",
    "gemini": "google",
    "deepseek": "deepseek",
    "llama": "groq",
    "mixtral": "mistral",
    "mistral": "mistral",
    "command": "cohere",
    "sonar": "perplexity",
    "pplx": "perplexity",
    "grok": "xai",
    "jamba": "ai21",
    "nemotron": "nvidia",
    "nim": "nvidia",
    "dbrx": "databricks",
}


class LLMGateway:
    def __init__(self, config: LargestackConfig | None = None):
        self.config = config or get_config()
        self.providers: dict[str, BaseProvider] = {}
        self.cost_tracker = CostTracker()
        self._cache = SemanticCache() if self.config.semantic_cache else None
        self._smart_router = None
        self._breakers: dict[str, CircuitBreaker] = {}
        self._init_providers()
        # Create circuit breakers for ALL registered providers (including Ollama)
        for name in self.providers:
            self._breakers[name] = CircuitBreaker(name)
        if self.config.smart_routing:
            from largestack._core.smart_router import SmartRouter

            self._smart_router = SmartRouter()

    def _init_providers(self):
        c = self.config
        if c.openai_api_key:
            from largestack._core.providers.openai_prov import OpenAIProvider

            self.providers["openai"] = OpenAIProvider(c.openai_api_key, c.openai_base_url)
        if c.openai_compatible_base_url:
            from largestack._core.providers.openai_prov import OpenAIProvider

            self.providers["local"] = OpenAIProvider(
                c.openai_compatible_api_key or "local", c.openai_compatible_base_url
            )
            self.providers["openai_compatible"] = self.providers["local"]
        if c.anthropic_api_key:
            from largestack._core.providers.anthropic_prov import AnthropicProvider

            self.providers["anthropic"] = AnthropicProvider(c.anthropic_api_key)
        if c.deepseek_api_key:
            from largestack._core.providers.deepseek_prov import DeepSeekProvider

            self.providers["deepseek"] = DeepSeekProvider(c.deepseek_api_key)
        if c.google_api_key:
            from largestack._core.providers.google_prov import GoogleProvider

            self.providers["google"] = GoogleProvider(c.google_api_key)
        if c.groq_api_key:
            from largestack._core.providers.groq_prov import GroqProvider

            self.providers["groq"] = GroqProvider(c.groq_api_key)
        if c.mistral_api_key:
            from largestack._core.providers.mistral_prov import MistralProvider

            self.providers["mistral"] = MistralProvider(c.mistral_api_key)
        if c.together_api_key:
            from largestack._core.providers.together_prov import TogetherProvider

            self.providers["together"] = TogetherProvider(c.together_api_key)
        if c.fireworks_api_key:
            from largestack._core.providers.fireworks_prov import FireworksProvider

            self.providers["fireworks"] = FireworksProvider(c.fireworks_api_key)
        if c.cohere_api_key:
            from largestack._core.providers.cohere_prov import CohereProvider

            self.providers["cohere"] = CohereProvider(c.cohere_api_key)
        if c.azure_openai_key and c.azure_openai_endpoint:
            from largestack._core.providers.azure_prov import AzureOpenAIProvider

            self.providers["azure"] = AzureOpenAIProvider(
                c.azure_openai_key, c.azure_openai_endpoint
            )
        if c.bedrock_region:
            try:
                from largestack._core.providers.bedrock_prov import BedrockProvider

                self.providers["bedrock"] = BedrockProvider(c.bedrock_region)
            except Exception as _e:
                log.debug(f"swallowed: {_e}")
        # New providers (OpenAI-compatible)
        for pname, key_field, pclass_path in [
            (
                "perplexity",
                "perplexity_api_key",
                "largestack._core.providers.perplexity_prov.PerplexityProvider",
            ),
            (
                "cerebras",
                "cerebras_api_key",
                "largestack._core.providers.cerebras_prov.CerebrasProvider",
            ),
            (
                "sambanova",
                "sambanova_api_key",
                "largestack._core.providers.sambanova_prov.SambaNovaProvider",
            ),
            (
                "openrouter",
                "openrouter_api_key",
                "largestack._core.providers.openrouter_prov.OpenRouterProvider",
            ),
            ("xai", "xai_api_key", "largestack._core.providers.xai_prov.XAIProvider"),
            ("ai21", "ai21_api_key", "largestack._core.providers.ai21_prov.AI21Provider"),
            ("lepton", "lepton_api_key", "largestack._core.providers.lepton_prov.LeptonProvider"),
            ("nvidia", "nvidia_api_key", "largestack._core.providers.nvidia_prov.NVIDIAProvider"),
        ]:
            key = getattr(c, key_field, "") or os.environ.get(
                f"LARGESTACK_{pname.upper()}_API_KEY", ""
            )
            if key:
                import importlib

                mod_path, cls_name = pclass_path.rsplit(".", 1)
                mod = importlib.import_module(mod_path)
                self.providers[pname] = getattr(mod, cls_name)(key)
        # P1: Ollama is opt-in (set LARGESTACK_ENABLE_OLLAMA=1 or config.ollama_enabled=True)
        # Defaults to enabled in development for backward compat; off by default in production.
        ollama_enabled = getattr(c, "ollama_enabled", None)
        if ollama_enabled is None:
            # Default: enabled unless production env
            ollama_enabled = getattr(c, "env", "development") != "production"
        if ollama_enabled:
            from largestack._core.providers.ollama_prov import OllamaProvider

            self.providers["ollama"] = OllamaProvider(c.ollama_base_url)
        if c.ollama_openai_compat:
            from largestack._core.providers.openai_prov import OpenAIProvider

            base = c.ollama_base_url.rstrip("/")
            self.providers["ollama_openai"] = OpenAIProvider("ollama", f"{base}/v1")
            # ergonomic alias: local/<model> uses Ollama OpenAI-compatible endpoint unless explicitly configured above
            self.providers.setdefault("local", self.providers["ollama_openai"])

        # v0.7.0: LiteLLM provider is registered when the optional package is
        # installed. Benchmarks use TestModel/local paths and should not import
        # LiteLLM because it can transitively load heavy ML libraries in a
        # constrained subprocess. Runtime behavior is unchanged outside that
        # explicit benchmark marker.
        if os.environ.get("LARGESTACK_BENCHMARK_SUBPROCESS", "").lower() not in (
            "1",
            "true",
            "yes",
        ):
            try:
                import litellm  # noqa: F401
                from largestack._core.providers.litellm_prov import LiteLLMProvider

                self.providers["litellm"] = LiteLLMProvider()
            except Exception as e:
                log.debug(f"litellm unavailable; litellm/* models unavailable: {e}")

    def _resolve_provider(self, model: str) -> tuple[str, BaseProvider]:
        if "/" in model:
            pn = model.split("/")[0]
        else:
            pn = "ollama"
            for prefix, provider in MODEL_PREFIX_MAP.items():
                if model.startswith(prefix):
                    pn = provider
                    break
        p = self.providers.get(pn)
        if not p:
            # Don't silently route to wrong provider — raise explicit error
            available = list(self.providers.keys())
            raise ProviderError(
                f"No provider configured for '{pn}' (model={model!r}). "
                f"Available providers: {available}. "
                f"Configure via LARGESTACK_{pn.upper()}_API_KEY env var or pass providers explicitly."
            )
        return pn, p

    async def aclose(self) -> None:
        """Close all provider clients owned by the gateway."""
        import asyncio
        import contextlib
        import inspect

        providers = getattr(self, "providers", {}) or {}
        for provider in list(providers.values()):
            close = getattr(provider, "aclose", None) or getattr(provider, "close", None)
            if close is None:
                continue
            with contextlib.suppress(Exception):
                result = close()
                if inspect.isawaitable(result):
                    await result

        with contextlib.suppress(Exception):
            await asyncio.sleep(0)
            await asyncio.sleep(0.10)

    async def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        agent_name: str = "default",
        **kw,
    ) -> LLMResponse:
        # v0.3.10: enforce largestack.testing.ALLOW_MODEL_REQUESTS gate.
        # Read at call time (not import time) so block_model_requests() works
        # for tests that flip the flag after the gateway was constructed.
        try:
            from largestack import testing as _t
            from largestack.errors import ModelRequestsBlockedError

            if not _t.ALLOW_MODEL_REQUESTS:
                raise ModelRequestsBlockedError(str(model))
        except ImportError:
            pass  # largestack.testing always importable; this is defensive only

        # Smart routing override
        if self._smart_router and model == "auto":
            tier = self._smart_router.estimate_complexity(messages, bool(tools))
            model = self._smart_router.select(tier)

        # P0-2 (v0.3.3): cache key must include behavior-affecting kwargs
        cache_kw = {
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": kw.get("response_format"),
            "tool_choice": kw.get("tool_choice"),
            "top_p": kw.get("top_p"),
            "seed": kw.get("seed"),
        }

        # Cache check
        if self._cache:
            cached = self._cache.get_exact(messages, model, **cache_kw)
            if cached:
                log.debug(f"Cache hit for {model}")
                return LLMResponse(**cached) if isinstance(cached, dict) else cached

        await bus.emit("llm.request", {"model": model, "agent": agent_name})
        pn, prov = self._resolve_provider(model)
        tried = [pn]
        success = False

        try:
            resp = await self._retry(prov, messages, model, tools, temperature, max_tokens, **kw)
            success = True
        except ProviderError as e:
            primary_error = e
            resp = None
            # Build fallback model list: same provider's model OR provider's default
            # User can configure provider-specific fallbacks via config.fallback_models
            fallback_models = getattr(self.config, "fallback_models", {})

            # Default fallbacks per provider
            default_fallbacks = {
                "openai": "gpt-4o-mini",
                "anthropic": "claude-haiku-4-5-20251001",
                "google": "gemini-2.5-flash",
                "deepseek": "deepseek-chat",
                "groq": "llama-3.3-70b-versatile",
                "cohere": "command-r-plus",
                "ollama": "llama3.2",
            }

            # Fallback: route through _retry so circuit breaker + retry semantics apply
            for n, fb in self.providers.items():
                if n == pn:
                    continue
                tried.append(n)
                bare_model = model.split("/", 1)[-1] if "/" in model else model
                fallback_model = fallback_models.get(model, default_fallbacks.get(n, bare_model))
                try:
                    resp = await self._retry(
                        fb, messages, fallback_model, tools, temperature, max_tokens, **kw
                    )
                    success = True
                    log.info(f"Fallback succeeded: {pn}→{n} (model: {fallback_model})")
                    break
                except ProviderError as fb_err:
                    log.debug(f"Fallback {n} also failed: {fb_err}")
                    continue
                except Exception as fb_err:
                    log.debug(f"Fallback {n} unexpected: {fb_err}")
                    continue
            if resp is None:
                raise AllProvidersFailedError(tried) from primary_error

        # Cost
        resp.cost = self.cost_tracker.calc(
            resp.model, resp.input_tokens, resp.output_tokens, resp.cached_tokens
        )
        self.cost_tracker.add(resp.cost, agent_name, tokens=resp.input_tokens + resp.output_tokens)

        # Cache store
        if self._cache:
            self._cache.put_exact(messages, model, resp, **cache_kw)

        # Metrics
        try:
            from largestack._observe.metrics import track_llm_call

            track_llm_call(
                resp.model, resp.input_tokens, resp.output_tokens, resp.cost, resp.latency_ms
            )
        except Exception as _e:
            log.debug(f"swallowed: {_e}")

        # Smart router update — track actual success, not finish_reason
        if self._smart_router:
            self._smart_router.update(model, success, resp.latency_ms, resp.cost)

        await bus.emit(
            "llm.response",
            {
                "model": resp.model,
                "cost": resp.cost,
                "latency_ms": resp.latency_ms,
                "agent": agent_name,
            },
        )
        return resp

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=1, max=8, jitter=1),
        retry=retry_if_exception_type(ProviderError),
        reraise=True,
    )
    async def _retry(self, prov, msgs, model, tools, temp, max_tok, **kw) -> LLMResponse:
        prov_name = prov.name
        breaker = self._breakers.get(prov_name)
        if breaker and not breaker.allow_request():
            raise ProviderError(f"Circuit OPEN for {prov_name} — skipping")
        try:
            resp = await prov.chat(
                messages=msgs, model=model, tools=tools, temperature=temp, max_tokens=max_tok, **kw
            )
            if breaker:
                breaker.record_success()
            return resp
        except ProviderError as e:
            if breaker:
                breaker.record_failure(e)
            raise

    async def stream(self, model: str, messages: list[dict], **kw) -> AsyncIterator[str]:
        # v0.3.10: enforce ALLOW_MODEL_REQUESTS gate (same as chat()).
        try:
            from largestack import testing as _t
            from largestack.errors import ModelRequestsBlockedError

            if not _t.ALLOW_MODEL_REQUESTS:
                raise ModelRequestsBlockedError(str(model))
        except ImportError:
            pass
        _, p = self._resolve_provider(model)
        async for tok in p.chat_stream(messages, model, **kw):
            yield tok

    async def close(self):
        for p in self.providers.values():
            if hasattr(p, "close"):
                await p.close()
