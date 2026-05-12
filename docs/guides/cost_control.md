# Guide: Cost Control

## Per-Run Budget

```python
agent = Agent(name="researcher", cost_budget=0.50)  # Max $0.50 per run
```

If the run exceeds this, `BudgetExceededError` is raised immediately.

## Pre-Execution Prediction

```python
from largestack._core.cost import CostTracker
tracker = CostTracker()
estimate = tracker.predict("gpt-4o-mini", input_tokens=5000)
print(f"Expected: ${estimate.expected:.4f} (range: ${estimate.low:.4f}–${estimate.high:.4f})")
```

## Choose Cheaper Models

| Model | Input/1M | Output/1M | Best For |
|-------|----------|-----------|----------|
| deepseek-chat | $0.14 | $0.28 | General tasks |
| gpt-4o-mini | $0.05 | $0.40 | Simple classification |
| gpt-4o-mini | $0.15 | $0.60 | Balanced quality/cost |
| claude-sonnet-4-6 | $3.00 | $15.00 | Complex reasoning |

## Smart Routing (auto-pick cheapest viable model)

```yaml
# largestack.yaml
smart_routing: true
```
```python
agent = Agent(name="auto", llm="auto")  # Thompson Sampling picks best model
```

## Semantic Caching

```yaml
semantic_cache: true  # Identical queries return cached response — $0 cost
```

## Monitor with CLI

```bash
largestack cost              # Total costs by agent
largestack cost --period=today  # Today's costs
```
