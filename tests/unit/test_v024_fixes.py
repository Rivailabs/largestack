"""Tests for v0.2.4 critical fixes."""

import sys, asyncio

sys.path.insert(0, ".")


def test_team_retries_zero_doesnt_raise_none():
    """team.py with retries=0 should still attempt once."""
    from largestack.team import Team
    from largestack import Agent

    class FailAgent(Agent):
        def __init__(self):
            self.name = "fail"
            self.fallback = None
            self.config = None

        async def run(self, *a, **kw):
            raise ValueError("bad")

    # Team with retries=0 should still attempt once and raise the underlying ValueError, not TypeError
    team = Team(agents=[FailAgent()], strategy="sequential", on_error="fail", retries_per_agent=0)
    try:
        asyncio.run(team.run("x"))
    except ValueError:
        pass  # expected
    except TypeError as e:
        # Old bug: "raise None" → TypeError
        assert False, f"team.py raises None bug: {e}"


def test_clone_forwards_guardrails():
    from largestack import Agent
    from largestack.guardrails import GuardrailPipeline

    a = Agent(name="orig", llm="openai/gpt-4o-mini", guardrails=GuardrailPipeline())
    b = a.clone()
    # Cloned agent must keep guardrails
    assert hasattr(b, "_guards")


def test_encryption_magic_prefix():
    from largestack._security.encryption import EncryptionManager

    enc = EncryptionManager(key=b"x" * 32)
    ct = enc.encrypt("hello")
    pt = enc.decrypt(ct)
    assert pt == "hello"
    # Verify magic prefix in raw bytes
    import base64

    raw = base64.b64decode(ct)
    assert raw[:3] == b"NX\x01"


def test_extract_final_answer_dict():
    from largestack._core.code_agent import CodeAgent

    a = CodeAgent()
    result = a.extract_final_answer('final_answer({"key": "val"})', "")
    assert result == {"key": "val"}


def test_extract_final_answer_nested_calls():
    from largestack._core.code_agent import CodeAgent

    a = CodeAgent()
    result = a.extract_final_answer('final_answer(json.dumps({"a": 1}))', "")
    # Should preserve inner structure (returns string of expression)
    assert "json.dumps" in str(result) or result == 'json.dumps({"a": 1})'


def test_metrics_real_buckets():
    from largestack._observe.metrics import MetricsCollector

    m = MetricsCollector()
    for v in [10, 50, 100, 500]:
        m.observe("test_latency", v)
    output = m.format_prometheus()
    assert "_bucket{le=" in output
    assert "_count" in output
    assert "_sum" in output


def test_eval_runner_concurrency():
    from largestack._evals.runner import EvalRunner, EvalCase

    class MockAgent:
        async def run(self, prompt):
            class R:
                content = "the answer is 42"

            return R()

    runner = EvalRunner(MockAgent(), concurrency=3)
    cases = [EvalCase(input=f"q{i}", expected="42") for i in range(10)]
    report = asyncio.run(runner.run(cases))
    assert report.passed == 10
    # All cases must have uniform shape (no missing keys)
    for c in report.cases:
        assert "expected" in c
        assert "actual" in c
        assert "passed" in c


def test_detect_production_requires_explicit():
    """Production should require explicit LARGESTACK_ENV=production."""
    from largestack._core.license import detect_production
    import os

    # Backup
    orig = os.environ.pop("LARGESTACK_ENV", None)
    try:
        is_prod, score, _ = detect_production()
        assert not is_prod  # No explicit env → not prod
    finally:
        if orig:
            os.environ["LARGESTACK_ENV"] = orig
