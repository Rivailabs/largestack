"""Cost must be non-zero for the DeepSeek models actually served by the API.

Regression guard for the bug where `deepseek-chat` is served as `deepseek-v4-flash`,
which was missing from the in-code PRICING table, so cost computed to $0 whenever
`pricing/models.yaml` was not in the current working directory (e.g. any deployed app).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from largestack._core.cost import PRICING, CostTracker


def test_served_deepseek_models_are_priced():
    tracker = CostTracker()
    for model in ("deepseek-chat", "deepseek-v4-flash", "deepseek-v4", "deepseek-reasoner"):
        assert tracker.calc(model, 1000, 500) > 0, f"{model} priced as $0"


def test_provider_prefixed_model_is_priced():
    # The gateway passes the bare model name; the agent string is provider-prefixed.
    assert CostTracker().calc("deepseek/deepseek-v4-flash", 1000, 500) > 0


def test_incode_pricing_covers_yaml_deepseek_models():
    # The in-code PRICING (what pip users get) must not drift behind pricing/models.yaml.
    yaml_path = Path(__file__).resolve().parents[2] / "pricing" / "models.yaml"
    if not yaml_path.exists():
        return  # yaml is a dev-only override; nothing to check
    data = yaml.safe_load(yaml_path.read_text()) or {}
    missing = [m for m in data if m.startswith("deepseek") and m not in PRICING]
    assert not missing, f"in-code PRICING missing DeepSeek models present in yaml: {missing}"
