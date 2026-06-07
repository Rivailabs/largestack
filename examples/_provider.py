"""Shared provider selection for runnable examples.

Examples prefer DeepSeek when ``LARGESTACK_DEEPSEEK_API_KEY`` is set, allow
``LARGESTACK_DEFAULT_MODEL`` as an explicit override, and fall back to OpenAI
only when an OpenAI key is present. No API key is printed or stored.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Awaitable, TypeVar

T = TypeVar("T")


class MissingProviderConfig(RuntimeError):
    """Raised when an example needs a cloud provider key that is not configured."""


def ensure_repo_on_path() -> None:
    repo = Path(__file__).resolve().parents[1]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))


def select_model() -> str:
    override = os.environ.get("LARGESTACK_DEFAULT_MODEL", "").strip()
    if override:
        provider = override.split("/", 1)[0]
        if provider == "deepseek" and not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
            raise MissingProviderConfig(
                "LARGESTACK_DEFAULT_MODEL selects DeepSeek, but LARGESTACK_DEEPSEEK_API_KEY is not set."
            )
        if provider == "openai" and not os.environ.get("LARGESTACK_OPENAI_API_KEY"):
            raise MissingProviderConfig(
                "LARGESTACK_DEFAULT_MODEL selects OpenAI, but LARGESTACK_OPENAI_API_KEY is not set."
            )
        return override
    if os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
        return "deepseek/deepseek-chat"
    if os.environ.get("LARGESTACK_OPENAI_API_KEY"):
        return "openai/gpt-4o-mini"
    raise MissingProviderConfig(
        "No provider key configured. Set LARGESTACK_DEEPSEEK_API_KEY for the default examples, "
        "or set LARGESTACK_OPENAI_API_KEY plus LARGESTACK_DEFAULT_MODEL=openai/gpt-4o-mini. "
        "For an offline quickstart, run examples/00_offline_test_model.py."
    )


async def run_with_timeout(awaitable: Awaitable[T], *, timeout: float = 120.0) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout)


async def close_quietly(obj) -> None:
    close = getattr(obj, "aclose", None) or getattr(obj, "close", None)
    if close is None:
        return
    with suppress(Exception):
        result = close()
        if hasattr(result, "__await__"):
            await result


def main_or_skip(coro_factory, *, timeout: float = 120.0) -> None:
    try:
        asyncio.run(run_with_timeout(coro_factory(), timeout=timeout))
    except MissingProviderConfig as exc:
        print(f"SKIP: {exc}")
        raise SystemExit(0) from exc
    except TimeoutError as exc:
        print(f"FAIL: example timed out after {timeout:.0f}s")
        raise SystemExit(1) from exc
