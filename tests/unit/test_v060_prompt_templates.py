"""v0.6.0: Prompt template system tests."""

from __future__ import annotations

import json
import random

import pytest

from largestack._core.prompt_templates import PromptRegistry, PromptTemplateError


# -------------------- Registration --------------------


def test_register_and_render_simple_template():
    reg = PromptRegistry()
    reg.register("greet", "Hello {name}!")
    assert reg.render("greet", name="alice") == "Hello alice!"


def test_register_validates_inputs():
    reg = PromptRegistry()
    with pytest.raises(PromptTemplateError):
        reg.register("", "template")  # empty name
    with pytest.raises(PromptTemplateError):
        reg.register("x", "tpl", version="")  # empty version
    # Empty template is allowed (could be a placeholder for fill-in-later)


def test_first_version_is_auto_active():
    reg = PromptRegistry()
    reg.register("greet", "v1 template", version="v1")
    assert reg.get_active("greet") == "v1"


def test_set_active_promotes_version():
    reg = PromptRegistry()
    reg.register("greet", "Hello {who} (v1)", version="v1")
    reg.register("greet", "Hi {who} (v2)", version="v2")
    assert reg.get_active("greet") == "v1"  # first registered = active by default

    reg.set_active("greet", "v2")
    assert reg.get_active("greet") == "v2"
    assert "v2" in reg.render("greet", who="bob")


def test_set_active_unknown_template_raises():
    reg = PromptRegistry()
    with pytest.raises(PromptTemplateError, match="unknown template"):
        reg.set_active("nonexistent", "v1")


def test_set_active_unknown_version_raises():
    reg = PromptRegistry()
    reg.register("greet", "tpl", version="v1")
    with pytest.raises(PromptTemplateError, match="not registered"):
        reg.set_active("greet", "v99")


def test_list_versions_and_templates():
    reg = PromptRegistry()
    reg.register("a", "tpl1", version="v1")
    reg.register("a", "tpl2", version="v2")
    reg.register("b", "tplx")
    assert reg.list_versions("a") == ["v1", "v2"]
    assert reg.list_templates() == ["a", "b"]


# -------------------- Rendering --------------------


def test_render_explicit_version_pins_correctly():
    reg = PromptRegistry()
    reg.register("greet", "Hello {who} v1", version="v1")
    reg.register("greet", "Hello {who} v2", version="v2")
    reg.set_active("greet", "v2")  # active = v2

    # Explicit version wins over active (positional after name)
    assert reg.render("greet", "v1", who="alice") == "Hello alice v1"
    # No version → use active
    assert reg.render("greet", who="alice") == "Hello alice v2"


def test_render_missing_variable_fails_loud():
    """v0.6: missing placeholder must raise, not silently render {x} as text."""
    reg = PromptRegistry()
    reg.register("g", "Hello {who}!")
    with pytest.raises(PromptTemplateError, match="missing variable"):
        reg.render("g")  # no who


def test_render_unknown_template_raises():
    reg = PromptRegistry()
    with pytest.raises(PromptTemplateError, match="unknown template"):
        reg.render("nonexistent", x=1)


def test_render_unknown_version_raises():
    reg = PromptRegistry()
    reg.register("g", "x", version="v1")
    with pytest.raises(PromptTemplateError, match="not registered"):
        reg.render("g", "v99")


def test_render_handles_user_var_named_name():
    """Regression: variable dict containing a `name` key must work
    (the original render(name=..., **vars) signature collided)."""
    reg = PromptRegistry()
    reg.register("g", "Hello {name} from {company}")
    out = reg.render("g", name="Sachith", company="RivaiLabs")
    assert out == "Hello Sachith from RivaiLabs"


def test_render_handles_user_var_named_version():
    """Same regression for `version` collision."""
    reg = PromptRegistry()
    reg.register("g", "Document version {version}")
    out = reg.render("g", version="v3.1")
    assert out == "Document version v3.1"


# -------------------- A/B split --------------------


def test_render_with_split_picks_only_v1_at_100_percent():
    """Deterministic with rng — full weight on v1 always picks v1."""
    reg = PromptRegistry()
    reg.register("g", "v1 text", version="v1")
    reg.register("g", "v2 text", version="v2")
    rng = random.Random(42)
    text, used = reg.render_with_split("g", split={"v1": 1, "v2": 0}, rng=rng)
    assert used == "v1"
    assert text == "v1 text"


def test_render_with_split_distributes_over_many_calls():
    """50/50 split — over many trials, both versions used roughly equally."""
    reg = PromptRegistry()
    reg.register("g", "v1", version="v1")
    reg.register("g", "v2", version="v2")
    rng = random.Random(123)
    counts = {"v1": 0, "v2": 0}
    for _ in range(2000):
        _, used = reg.render_with_split("g", split={"v1": 1, "v2": 1}, rng=rng)
        counts[used] += 1
    # Each should be in [800, 1200] for 50/50 with 2000 samples (very wide bound)
    assert 800 < counts["v1"] < 1200
    assert 800 < counts["v2"] < 1200


def test_render_with_split_validates():
    reg = PromptRegistry()
    reg.register("g", "v1", version="v1")
    with pytest.raises(PromptTemplateError, match="non-empty"):
        reg.render_with_split("g", split={})
    with pytest.raises(PromptTemplateError, match="not registered"):
        reg.render_with_split("g", split={"v99": 1})
    with pytest.raises(PromptTemplateError, match="sum to > 0"):
        reg.render_with_split("g", split={"v1": 0})


def test_render_with_split_returns_version_used():
    """The (text, version) tuple lets callers log which arm was shown."""
    reg = PromptRegistry()
    reg.register("g", "X", version="v1")
    rng = random.Random(0)
    text, used = reg.render_with_split("g", split={"v1": 1}, rng=rng)
    assert used == "v1"
    assert text == "X"


# -------------------- Usage counters --------------------


def test_usage_counts_track_renders():
    reg = PromptRegistry()
    reg.register("g", "X", version="v1")
    reg.register("g", "Y", version="v2")
    reg.render("g", "v1")  # positional version
    reg.render("g", "v1")
    reg.render("g", "v2")
    counts = reg.usage_counts("g")
    assert counts["v1"] == 2
    assert counts["v2"] == 1


def test_usage_counts_unknown_template_returns_empty():
    reg = PromptRegistry()
    assert reg.usage_counts("nope") == {}


# -------------------- Persistence --------------------


def test_persist_to_disk_and_reload(tmp_path):
    path = str(tmp_path / "prompts.json")
    reg = PromptRegistry(persist_path=path)
    reg.register("greet", "Hi {who}", version="v1")
    reg.register("greet", "Hello {who}!", version="v2")
    reg.set_active("greet", "v2")

    # File must exist on disk now
    with open(path) as f:
        data = json.load(f)
    assert "greet" in data["templates"]
    assert data["active"]["greet"] == "v2"

    # New registry with same path = reloaded state
    reg2 = PromptRegistry(persist_path=path)
    assert reg2.get_active("greet") == "v2"
    assert reg2.render("greet", who="alice") == "Hello alice!"


def test_persist_handles_missing_file_gracefully(tmp_path):
    path = str(tmp_path / "does_not_exist.json")
    reg = PromptRegistry(persist_path=path)  # must not raise
    assert reg.list_templates() == []
