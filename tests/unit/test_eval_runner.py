import sys, asyncio

sys.path.insert(0, ".")


def test_eval_runner_basic():
    from largestack._evals.runner import EvalRunner, EvalCase, EvalReport

    class MockAgent:
        async def run(self, prompt):
            class R:
                content = "answer is 42"

            return R()

    runner = EvalRunner(MockAgent())
    cases = [EvalCase(input="x", expected="42"), EvalCase(input="y", expected="42")]
    report = asyncio.run(runner.run(cases))
    assert report.total == 2
    assert report.passed == 2
    assert report.pass_rate == 1.0


def test_eval_case():
    from largestack._evals.runner import EvalCase

    c = EvalCase(input="q", expected="a", metadata={"tag": "math"})
    assert c.metadata["tag"] == "math"
