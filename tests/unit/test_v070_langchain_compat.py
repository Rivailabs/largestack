"""v0.7.0: LangChain compat adapter tests.

Mocks LangChain objects so we don't need langchain-core installed
to test the wrappers' behavior.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def fake_langchain():
    """Inject a minimal langchain_core module into sys.modules."""
    fake_mod = MagicMock()
    with patch.dict("sys.modules", {"langchain_core": fake_mod}):
        yield fake_mod


# -------------------- wrap_tool --------------------


@pytest.mark.asyncio
async def test_wrap_tool_basic_async(fake_langchain):
    """A LangChain tool with arun() must be wrapped and callable."""
    from largestack._integrations.langchain_compat import wrap_tool

    lc_tool = MagicMock()
    lc_tool.name = "search_web"
    lc_tool.description = "Search the web"
    lc_tool.arun = AsyncMock(return_value="search result")
    lc_tool.run = MagicMock()  # also exists but we prefer arun
    lc_tool.args_schema = None

    wrapped = wrap_tool(lc_tool)
    assert wrapped._tool_schema["name"] == "search_web"
    assert wrapped._tool_schema["description"] == "Search the web"

    result = await wrapped(input="test query")
    assert result == "search result"
    lc_tool.arun.assert_awaited_once_with("test query")


@pytest.mark.asyncio
async def test_wrap_tool_sync_only_offloads_to_thread(fake_langchain):
    """A sync-only LangChain tool must be wrapped via asyncio.to_thread."""
    from largestack._integrations.langchain_compat import wrap_tool

    lc_tool = MagicMock(spec=["name", "description", "run", "args_schema"])
    lc_tool.name = "calc"
    lc_tool.description = "Calculator"
    lc_tool.run = MagicMock(return_value="42")
    lc_tool.args_schema = None
    # Explicitly no arun
    if hasattr(lc_tool, "arun"):
        del lc_tool.arun

    wrapped = wrap_tool(lc_tool)
    result = await wrapped(input="2+2")
    assert result == "42"
    lc_tool.run.assert_called_once_with("2+2")


@pytest.mark.asyncio
async def test_wrap_tool_kwargs_passed_to_arun_when_no_input_key(fake_langchain):
    """If kwargs has multiple keys (no single 'input'), pass dict to arun."""
    from largestack._integrations.langchain_compat import wrap_tool

    lc_tool = MagicMock()
    lc_tool.name = "complex_tool"
    lc_tool.description = "..."
    lc_tool.arun = AsyncMock(return_value="ok")
    lc_tool.args_schema = None

    wrapped = wrap_tool(lc_tool)
    await wrapped(query="q", limit=10)
    lc_tool.arun.assert_awaited_once_with({"query": "q", "limit": 10})


@pytest.mark.asyncio
async def test_wrap_tool_returns_error_string_on_exception(fake_langchain):
    """Tool exceptions must be caught and returned as error strings."""
    from largestack._integrations.langchain_compat import wrap_tool

    lc_tool = MagicMock()
    lc_tool.name = "broken"
    lc_tool.description = "..."
    lc_tool.arun = AsyncMock(side_effect=RuntimeError("network down"))
    lc_tool.args_schema = None

    wrapped = wrap_tool(lc_tool)
    result = await wrapped(input="x")
    assert "broken failed" in result
    assert "network down" in result


def test_wrap_tool_preserves_args_schema(fake_langchain):
    """If LangChain tool has args_schema, the JSON Schema must be attached."""
    from largestack._integrations.langchain_compat import wrap_tool

    schema_dict = {"type": "object", "properties": {"q": {"type": "string"}}}

    fake_schema = MagicMock()
    fake_schema.model_json_schema = MagicMock(return_value=schema_dict)

    lc_tool = MagicMock()
    lc_tool.name = "schema_tool"
    lc_tool.description = "..."
    lc_tool.arun = AsyncMock()
    lc_tool.args_schema = fake_schema

    wrapped = wrap_tool(lc_tool)
    assert hasattr(wrapped, "_lc_schema")
    assert wrapped._lc_schema == schema_dict


# -------------------- wrap_loader --------------------


@pytest.mark.asyncio
async def test_wrap_loader_basic(fake_langchain):
    """A LangChain loader's load() returns Documents → list of dicts."""
    from largestack._integrations.langchain_compat import wrap_loader

    fake_doc1 = MagicMock()
    fake_doc1.page_content = "Page 1 content"
    fake_doc1.metadata = {"source": "/tmp/doc.pdf", "page": 0}

    fake_doc2 = MagicMock()
    fake_doc2.page_content = "Page 2 content"
    fake_doc2.metadata = {"source": "/tmp/doc.pdf", "page": 1}

    lc_loader = MagicMock(spec=["load", "__class__"])
    lc_loader.load = MagicMock(return_value=[fake_doc1, fake_doc2])
    lc_loader.__class__.__name__ = "PDFLoader"

    wrapped = wrap_loader(lc_loader)
    docs = await wrapped()

    assert len(docs) == 2
    assert docs[0]["content"] == "Page 1 content"
    assert docs[0]["metadata"]["page"] == 0
    assert docs[1]["content"] == "Page 2 content"


@pytest.mark.asyncio
async def test_wrap_loader_handles_aload(fake_langchain):
    """If loader has aload(), prefer it over load()."""
    from largestack._integrations.langchain_compat import wrap_loader

    fake_doc = MagicMock()
    fake_doc.page_content = "async loaded"
    fake_doc.metadata = {}

    lc_loader = MagicMock()
    lc_loader.aload = AsyncMock(return_value=[fake_doc])
    lc_loader.load = MagicMock()
    lc_loader.__class__.__name__ = "AsyncLoader"

    wrapped = wrap_loader(lc_loader)
    docs = await wrapped()
    assert docs[0]["content"] == "async loaded"
    lc_loader.aload.assert_awaited_once()


def test_wrap_loader_rejects_non_loader(fake_langchain):
    from largestack._integrations.langchain_compat import wrap_loader

    bad = MagicMock(spec=["__class__"])
    if hasattr(bad, "load"):
        del bad.load
    with pytest.raises(ValueError, match="not a LangChain loader"):
        wrap_loader(bad)


@pytest.mark.asyncio
async def test_wrap_loader_returns_empty_on_error(fake_langchain):
    """Loader errors are caught; empty list returned (with a log warning)."""
    from largestack._integrations.langchain_compat import wrap_loader

    lc_loader = MagicMock()
    lc_loader.load = MagicMock(side_effect=RuntimeError("file missing"))
    lc_loader.__class__.__name__ = "BrokenLoader"
    if hasattr(lc_loader, "aload"):
        del lc_loader.aload

    wrapped = wrap_loader(lc_loader)
    docs = await wrapped()
    assert docs == []


# -------------------- wrap_retriever --------------------


@pytest.mark.asyncio
async def test_wrap_retriever_with_ainvoke(fake_langchain):
    """Modern LangChain retrievers use ainvoke()."""
    from largestack._integrations.langchain_compat import wrap_retriever

    fake_doc = MagicMock()
    fake_doc.page_content = "relevant doc"
    fake_doc.metadata = {"score": 0.9}

    lc_ret = MagicMock(spec=["ainvoke", "__class__"])
    lc_ret.ainvoke = AsyncMock(return_value=[fake_doc])
    lc_ret.__class__.__name__ = "BM25Retriever"

    wrapped = wrap_retriever(lc_ret)
    results = await wrapped("search query", k=3)
    assert len(results) == 1
    assert results[0]["content"] == "relevant doc"


@pytest.mark.asyncio
async def test_wrap_retriever_falls_back_to_sync(fake_langchain):
    """Older retrievers only have get_relevant_documents — must work."""
    from largestack._integrations.langchain_compat import wrap_retriever

    fake_doc = MagicMock()
    fake_doc.page_content = "old api"
    fake_doc.metadata = {}

    lc_ret = MagicMock(spec=["get_relevant_documents", "__class__"])
    lc_ret.get_relevant_documents = MagicMock(return_value=[fake_doc])
    lc_ret.__class__.__name__ = "OldRetriever"

    wrapped = wrap_retriever(lc_ret)
    results = await wrapped("query")
    assert results[0]["content"] == "old api"


@pytest.mark.asyncio
async def test_wrap_retriever_applies_k_limit(fake_langchain):
    """k=2 must truncate results even if retriever returns more."""
    from largestack._integrations.langchain_compat import wrap_retriever

    docs = []
    for i in range(5):
        d = MagicMock()
        d.page_content = f"doc{i}"
        d.metadata = {}
        docs.append(d)

    lc_ret = MagicMock(spec=["ainvoke", "__class__"])
    lc_ret.ainvoke = AsyncMock(return_value=docs)
    lc_ret.__class__.__name__ = "Retriever"

    wrapped = wrap_retriever(lc_ret)
    results = await wrapped("query", k=2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_wrap_retriever_handles_exception(fake_langchain):
    from largestack._integrations.langchain_compat import wrap_retriever

    lc_ret = MagicMock(spec=["ainvoke", "__class__"])
    lc_ret.ainvoke = AsyncMock(side_effect=RuntimeError("idx down"))
    lc_ret.__class__.__name__ = "Bad"

    wrapped = wrap_retriever(lc_ret)
    results = await wrapped("q")
    assert results == []


# -------------------- ImportError path --------------------


def test_ensure_langchain_raises_clear_error_when_missing():
    """If langchain_core isn't installed, raise informative ImportError."""
    from largestack._integrations.langchain_compat import _ensure_langchain

    if "langchain_core" in sys.modules:
        # Skip if real langchain is present
        pytest.skip("langchain_core is actually installed")

    with patch.dict("sys.modules", {"langchain_core": None}):
        with pytest.raises(ImportError, match="langchain-core"):
            _ensure_langchain()
