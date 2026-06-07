from largestack._core.cost import CostTracker
from largestack.errors import BudgetExceededError


def test_calc():
    t = CostTracker()
    c = t.calc("gpt-4o-mini", 1000, 500)
    assert 0 < c < 0.01


def test_tracking():
    t = CostTracker()
    t.add(0.01)
    t.add(0.02)
    assert t.run_cost == 0.03


def test_budget():
    t = CostTracker()
    t.add(5.01)
    try:
        t.check(5.0)
        assert False
    except BudgetExceededError:
        pass


def test_predict():
    t = CostTracker()
    e = t.predict("gpt-4o-mini", 1000)
    assert e.low < e.expected < e.high
