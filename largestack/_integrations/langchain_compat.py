"""LangChain compatibility adapters (v0.7.0).

Lets LARGESTACK users tap into LangChain's 700+ ecosystem of tools, document
loaders, and retrievers without rebuilding wrappers ourselves. The
adapter takes any LangChain object and returns a LARGESTACK equivalent
that plays nicely with our @tool decorator, agent loop, and audit
trail.

Three adapters provided:

1. ``wrap_tool(lc_tool)`` — LangChain ``BaseTool`` → LARGESTACK ``@tool`` callable
2. ``wrap_loader(lc_loader)`` — LangChain ``BaseLoader`` → LARGESTACK document loader
3. ``wrap_retriever(lc_retriever)`` — LangChain ``BaseRetriever`` → LARGESTACK retriever

Usage:

    from langchain_community.tools import DuckDuckGoSearchRun
    from largestack._integrations.langchain_compat import wrap_tool
    from largestack import Agent

    # LangChain has it, you don't have to write it
    duckduckgo = DuckDuckGoSearchRun()
    largestack_tool = wrap_tool(duckduckgo)

    agent = Agent(name="search", llm="...", tools=[largestack_tool])
    await agent.run("What's the weather in Bengaluru?")

This single module unlocks ~700 LangChain integrations without LARGESTACK
having to maintain them. Behavior:
- LangChain tool errors are caught and returned as strings (so agent loop
  survives transport failures)
- The wrapped tool's name and description are preserved
- LangChain async tools (``BaseTool.arun``) are awaited; sync tools are
  offloaded to a thread

Requires: ``pip install langchain-core`` (or any langchain-* package
that depends on it). Without LangChain installed, this module raises
clear ImportError on first use.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable

from largestack._core.tools import tool

log = logging.getLogger("largestack.langchain_compat")


def _ensure_langchain():
    """Ensure langchain-core is installed; raise ImportError if not."""
    try:
        import langchain_core  # noqa: F401
        return True
    except ImportError as e:
        raise ImportError(
            "LangChain compat needs: pip install langchain-core "
            "(or any langchain-* package such as langchain-community)."
        ) from e


def wrap_tool(lc_tool: Any) -> Callable:
    """Wrap a LangChain tool as a LARGESTACK ``@tool``-decorated callable.

    Args:
        lc_tool: A LangChain ``BaseTool`` (or anything with ``.name``,
            ``.description``, ``.args_schema``, and either ``arun`` or ``run``).

    Returns:
        A LARGESTACK-compatible async callable that the agent can use.

    Behavior on errors:
        Catches all exceptions from the underlying LangChain tool and
        returns them as error strings — preserving the agent loop instead
        of bubbling up the exception. This matches LARGESTACK's MCPToolAdapter
        and tool-error conventions.
    """
    _ensure_langchain()

    name = getattr(lc_tool, "name", lc_tool.__class__.__name__)
    description = getattr(lc_tool, "description", "") or f"LangChain tool {name}"

    has_arun = hasattr(lc_tool, "arun") and callable(lc_tool.arun)
    has_run = hasattr(lc_tool, "run") and callable(lc_tool.run)

    @tool(name=name, description=description, timeout=60)
    async def _bridge(**kwargs) -> str:
        try:
            if has_arun:
                # LangChain async tool — supports either single str or kwargs
                if len(kwargs) == 1 and "input" in kwargs:
                    result = await lc_tool.arun(kwargs["input"])
                else:
                    result = await lc_tool.arun(kwargs)
            elif has_run:
                # Sync tool: offload to thread to avoid blocking event loop
                if len(kwargs) == 1 and "input" in kwargs:
                    result = await asyncio.to_thread(lc_tool.run, kwargs["input"])
                else:
                    result = await asyncio.to_thread(lc_tool.run, kwargs)
            else:
                return f"LangChain tool {name!r} has neither arun nor run"
            return str(result) if result is not None else ""
        except Exception as e:
            return f"LangChain tool {name} failed: {e}"

    # Preserve LangChain args schema if available — gives the LLM
    # the right parameter types/required fields
    schema = getattr(lc_tool, "args_schema", None)
    if schema is not None:
        try:
            # LangChain uses Pydantic v1 or v2 schemas — try both
            if hasattr(schema, "model_json_schema"):
                json_schema = schema.model_json_schema()
            elif hasattr(schema, "schema"):
                json_schema = schema.schema()
            else:
                json_schema = None
            if json_schema:
                _bridge._lc_schema = json_schema  # type: ignore
                _bridge.parameters = json_schema  # type: ignore
        except Exception as e:
            log.debug(f"Couldn't extract args_schema from {name}: {e}")

    return _bridge


def wrap_loader(lc_loader: Any) -> Callable:
    """Wrap a LangChain document loader as a LARGESTACK-compatible callable.

    Args:
        lc_loader: A LangChain ``BaseLoader`` instance (one with a
            ``load()`` method that returns ``list[Document]``).

    Returns:
        An async callable that returns a list of dicts, each with
        ``content`` and ``metadata`` keys. The dict shape matches
        LARGESTACK's RAG ingestion pipeline.

    Note: LangChain loaders are mostly sync; we offload to a thread.
    """
    _ensure_langchain()

    if not hasattr(lc_loader, "load"):
        raise ValueError(f"{lc_loader!r} is not a LangChain loader (no .load() method)")

    name = lc_loader.__class__.__name__

    async def _load() -> list[dict]:
        """Load documents via the wrapped LangChain loader."""
        try:
            # Some LangChain loaders have aload(); prefer that if present
            if hasattr(lc_loader, "aload") and callable(lc_loader.aload):
                docs = await lc_loader.aload()
            else:
                docs = await asyncio.to_thread(lc_loader.load)
        except Exception as e:
            log.warning(f"LangChain loader {name} failed: {e}")
            return []

        return [
            {
                "content": getattr(d, "page_content", str(d)),
                "metadata": dict(getattr(d, "metadata", {}) or {}),
            }
            for d in docs
        ]

    _load.__name__ = f"langchain_{name}_loader"
    _load.__doc__ = f"Async wrapper around LangChain {name} document loader."
    return _load


def wrap_retriever(lc_retriever: Any) -> Callable:
    """Wrap a LangChain retriever as a LARGESTACK-compatible search callable.

    Args:
        lc_retriever: A LangChain ``BaseRetriever`` (one with
            ``get_relevant_documents()`` or ``aget_relevant_documents()``).

    Returns:
        An async callable ``search(query: str, k: int = 4) -> list[dict]``.
    """
    _ensure_langchain()

    name = lc_retriever.__class__.__name__

    has_async = hasattr(lc_retriever, "aget_relevant_documents") and callable(
        lc_retriever.aget_relevant_documents
    )
    has_async2 = hasattr(lc_retriever, "ainvoke") and callable(lc_retriever.ainvoke)
    has_sync = hasattr(lc_retriever, "get_relevant_documents") and callable(
        lc_retriever.get_relevant_documents
    )
    has_sync2 = hasattr(lc_retriever, "invoke") and callable(lc_retriever.invoke)

    async def _search(query: str, k: int = 4) -> list[dict]:
        """Search the wrapped LangChain retriever."""
        try:
            if has_async2:
                docs = await lc_retriever.ainvoke(query)
            elif has_async:
                docs = await lc_retriever.aget_relevant_documents(query)
            elif has_sync2:
                docs = await asyncio.to_thread(lc_retriever.invoke, query)
            elif has_sync:
                docs = await asyncio.to_thread(lc_retriever.get_relevant_documents, query)
            else:
                return [{"error": f"{name} has no usable retrieval method"}]
        except Exception as e:
            log.warning(f"LangChain retriever {name} failed: {e}")
            return []

        # Apply k limit (LangChain retrievers usually self-limit, but enforce)
        if k > 0:
            docs = docs[:k]
        return [
            {
                "content": getattr(d, "page_content", str(d)),
                "metadata": dict(getattr(d, "metadata", {}) or {}),
            }
            for d in docs
        ]

    _search.__name__ = f"langchain_{name}_retriever"
    _search.__doc__ = f"Async wrapper around LangChain {name} retriever."
    return _search
