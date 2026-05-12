# Guide: Testing Agents

## Statistical Testing with SPRT

```python
from largestack._test.assertions import SPRT

sprt = SPRT(h0_rate=0.7, h1_rate=0.9)  # H0: 70% pass, H1: 90% pass
for run in range(100):
    success = run_agent_test()
    verdict = sprt.update(success)
    if verdict:
        print(f"Verdict after {run+1} runs: {verdict}")
        break  # PASS or FAIL — no need to run more
# Typically terminates in 22 runs instead of 100 (78% savings)
```

## Record/Replay for CI

```python
from largestack._test.recorder import Recorder

# Record live interactions
with Recorder("tests/fixtures/research.json") as rec:
    result = await agent.run("AI trends")
    rec.record(messages, response, model)

# Replay deterministically in CI (no API key needed)
from largestack._test.replayer import Replayer
with Replayer("tests/fixtures/research.json") as rep:
    response = rep.next_response()  # Returns recorded LLMResponse
```

## CI/CD Quality Gates

```python
from largestack._test.ci_gates import QualityGate

gate = QualityGate(thresholds={
    "task_completion": (">=", 0.85),
    "tool_correctness": (">=", 0.90),
    "cost_per_run": ("<=", 1.00),
})
results = gate.check({"task_completion": 0.92, "tool_correctness": 0.95, "cost_per_run": 0.45})
print(gate.format_report(results))
# Quality Gate: PASSED ✅
#   ✅ task_completion: 0.92 (threshold: 0.85)
#   ✅ tool_correctness: 0.95 (threshold: 0.90)
#   ✅ cost_per_run: 0.45 (threshold: 1.0)
```

## 6 Agent Metrics

```python
from largestack._test.eval_metrics import AgentMetrics

metrics = AgentMetrics.evaluate(
    result,
    expected_tools=["web_search", "calculator"],
    optimal_steps=3,
)
# {"task_completion": 1.0, "tool_correctness": 1.0, "step_efficiency": 0.75}
```
