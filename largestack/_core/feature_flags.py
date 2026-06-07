"""Feature flags — toggle features at runtime without redeployment."""

from __future__ import annotations
import os, json, time
from typing import Any


class FeatureFlags:
    """Runtime feature toggles (LaunchDarkly pattern).

    Sources: environment variables, JSON file, or in-memory.
    """

    def __init__(self, config_path: str = None):
        self._flags: dict[str, bool] = {}
        self._overrides: dict[str, bool] = {}
        if config_path and os.path.exists(config_path):
            with open(config_path) as f:
                self._flags = json.load(f)

    def is_enabled(self, flag: str, default: bool = False) -> bool:
        """Check if a feature flag is enabled."""
        # Priority: override → env → config → default
        if flag in self._overrides:
            return self._overrides[flag]
        env_val = os.environ.get(f"LARGESTACK_FF_{flag.upper()}")
        if env_val is not None:
            return env_val.lower() in ("1", "true", "yes")
        return self._flags.get(flag, default)

    def set(self, flag: str, enabled: bool):
        """Set a feature flag at runtime."""
        self._overrides[flag] = enabled

    def toggle(self, flag: str):
        """Toggle a feature flag."""
        current = self.is_enabled(flag)
        self._overrides[flag] = not current

    def list_flags(self) -> dict[str, bool]:
        all_flags = {**self._flags, **self._overrides}
        return all_flags


# Global instance
flags = FeatureFlags()
