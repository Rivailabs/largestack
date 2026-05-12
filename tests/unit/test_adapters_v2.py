"""Tests for v0.2.1 adapters."""
import asyncio, sys; sys.path.insert(0, ".")

def test_e2b_sandbox_local_fallback():
    from largestack._core.e2b_sandbox import E2BSandbox
    sb = E2BSandbox()
    result = asyncio.run(sb.run_python("print(2+2)"))
    assert "4" in result.stdout

def test_e2b_sandbox_timeout():
    from largestack._core.e2b_sandbox import E2BSandbox
    sb = E2BSandbox()
    result = asyncio.run(sb.run_python("import time; time.sleep(10)", timeout=1))
    assert result.exit_code != 0

def test_composio_toolset_apps():
    from largestack._core.composio_adapter import ComposioToolset
    ts = ComposioToolset()
    apps = ts.list_apps()
    assert "github" in apps
    assert "slack" in apps
    assert len(apps) >= 30

def test_mem0_memory_unavailable_handling():
    from largestack._memory.external_adapters import Mem0Memory
    mem = Mem0Memory(api_key=None)
    # Should not crash even without key
    result = asyncio.run(mem.search("test"))
    assert result == []

def test_zep_memory_unavailable_handling():
    from largestack._memory.external_adapters import ZepMemory
    mem = ZepMemory(api_key=None)
    result = asyncio.run(mem.search("test"))
    assert result == []

def test_ragas_fallback_eval():
    from largestack._evals import RagasAdapter
    adapter = RagasAdapter()
    results = asyncio.run(adapter.evaluate_rag(
        question="What is Python?",
        answer="Python is a programming language.",
        contexts=["Python is a high-level programming language."],
    ))
    assert "answer_relevancy" in results
    assert "faithfulness" in results

def test_eval_result_dataclass():
    from largestack._evals.adapters import EvalResult
    r = EvalResult("relevancy", 0.85, True)
    assert r.metric == "relevancy"
    assert r.score == 0.85
    assert r.passed
