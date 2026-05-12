"""Abstract base for LLM providers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from largestack.types import LLMResponse

class BaseProvider(ABC):
    name: str = "base"
    supports_streaming: bool = True
    supports_tools: bool = True

    @abstractmethod
    async def chat(self, messages: list[dict], model: str, tools: list[dict]|None=None,
                   stream: bool=False, temperature: float=0.7, max_tokens: int|None=None, **kw) -> LLMResponse: ...

    @abstractmethod
    async def chat_stream(self, messages: list[dict], model: str, tools: list[dict]|None=None, **kw) -> AsyncIterator[str]: ...

    @abstractmethod
    def count_tokens(self, text: str, model: str) -> int: ...

    def get_model(self, model: str) -> str:
        return model.split("/", 1)[1] if "/" in model else model

    async def close(self): pass
