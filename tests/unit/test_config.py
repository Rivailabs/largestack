from largestack._core.config import LargestackConfig


def test_defaults():
    c = LargestackConfig()
    assert c.max_turns == 25 and c.cost_budget == 5.0 and c.trace_enabled is True


def test_env_override(monkeypatch):
    monkeypatch.setenv("LARGESTACK_MAX_TURNS", "50")
    c = LargestackConfig()
    assert c.max_turns == 50
