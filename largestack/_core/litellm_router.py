"""LiteLLM-based universal LLM router — adds 100+ providers in one dependency.

Usage:
    from largestack._core.litellm_router import LiteLLMProvider

    # Now supports any LiteLLM model string:
    agent = Agent(llm="groq/llama-3.3-70b")
    agent = Agent(llm="bedrock/anthropic.claude-3-5-sonnet-v2")
    agent = Agent(llm="vertex_ai/gemini-2.0-flash")
"""

from __future__ import annotations
import logging
import os
from typing import Any

log = logging.getLogger("largestack.litellm")


class LiteLLMProvider:
    """Universal provider via LiteLLM. Supports 100+ models.

    Falls back gracefully if litellm not installed.
    """

    def __init__(self):
        self._available = False
        try:
            import litellm

            self._litellm = litellm
            self._available = True
            litellm.drop_params = True  # Don't error on unsupported params
        except ImportError:
            log.warning("litellm not installed. Install: pip install largestack[litellm]")

    @property
    def available(self) -> bool:
        return self._available

    async def chat(
        self,
        messages: list,
        model: str,
        tools: list | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict:
        """Chat via LiteLLM."""
        if not self._available:
            raise RuntimeError("litellm not installed. pip install litellm")

        # Build params
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            params["tools"] = self._format_tools(tools)

        # Use API key from environment if LARGESTACK_<PROVIDER>_API_KEY exists
        provider = model.split("/")[0].upper()
        largestack_key = os.environ.get(f"LARGESTACK_{provider}_API_KEY")
        if largestack_key:
            params["api_key"] = largestack_key

        try:
            response = await self._litellm.acompletion(**params)
            return self._normalize_response(response)
        except Exception as e:
            log.error(f"LiteLLM error for {model}: {e}")
            raise

    def _format_tools(self, tools: list) -> list:
        """Convert LARGESTACK tools to OpenAI function format."""
        formatted = []
        for t in tools:
            if hasattr(t, "name"):
                # Tool object
                formatted.append(
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": getattr(t, "description", ""),
                            "parameters": getattr(t, "schema", {}),
                        },
                    }
                )
            elif isinstance(t, dict):
                if "type" in t and t["type"] == "function":
                    formatted.append(t)
                else:
                    formatted.append({"type": "function", "function": t})
        return formatted

    def _normalize_response(self, response) -> dict:
        """Normalize LiteLLM response to LARGESTACK format."""
        try:
            choice = response.choices[0]
            msg = choice.message

            content = msg.content or ""
            tool_calls = []
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    )

            usage = response.usage
            return {
                "content": content,
                "tool_calls": tool_calls,
                "usage": {
                    "input_tokens": usage.prompt_tokens,
                    "output_tokens": usage.completion_tokens,
                },
                "model": response.model,
                "finish_reason": choice.finish_reason,
            }
        except Exception as e:
            log.error(f"Failed to normalize LiteLLM response: {e}")
            return {"content": str(response), "tool_calls": [], "usage": {}}

    @property
    def supported_models(self) -> list[str]:
        """Return common LiteLLM model strings."""
        return [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4-turbo",
            "anthropic/claude-3-5-sonnet-20241022",
            "anthropic/claude-3-5-haiku-20241022",
            "groq/llama-3.3-70b-versatile",
            "groq/llama-3.1-8b-instant",
            "deepseek/deepseek-chat",
            "deepseek/deepseek-reasoner",
            "together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "fireworks_ai/accounts/fireworks/models/llama-v3p3-70b-instruct",
            "vertex_ai/gemini-2.0-flash-exp",
            "vertex_ai/gemini-1.5-pro",
            "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0",
            "azure/gpt-4o",
            "ollama/llama3.3",
            "xai/grok-2-latest",
            "perplexity/llama-3.1-sonar-large-128k-online",
            "cerebras/llama-3.3-70b",
            "mistral/mistral-large-latest",
            "cohere/command-r-plus",
            "replicate/meta/llama-3.3-70b-instruct",
        ]
