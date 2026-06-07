"""Prompt template registry with versioning (v0.6.0).

Goals:
- Define named prompt templates with placeholders.
- Maintain multiple versions of the same prompt for A/B testing.
- Render templates with variables, with strict missing-variable detection.
- Persist templates to a JSON file (optional) for cross-process sharing.
- Track version usage for analytics (which version was rendered when).

Why this exists:
- Hardcoding prompts in code means deploys to change them.
- Templates make A/B testing trivial: route 10% of traffic to v2.
- Versioning means rolling back is just `set_active("greeting", "v1")`.

Usage:

    from largestack._core.prompt_templates import PromptRegistry

    reg = PromptRegistry()

    reg.register("greeting", "Hello {name}, welcome to {company}.", version="v1")
    reg.register(
        "greeting",
        "Hi {name}! Welcome to {company} — let's get started.",
        version="v2",
    )

    reg.set_active("greeting", "v2")
    text = reg.render("greeting", name="Sachith", company="RivaiLabs")
    # "Hi Sachith! Welcome to RivaiLabs — let's get started."

For A/B testing:
    text = reg.render_with_split("greeting", split={"v1": 50, "v2": 50},
                                 name="Sachith", company="RivaiLabs")
"""

from __future__ import annotations
import json
import logging
import random
import string
import time
from collections import Counter
from threading import Lock

log = logging.getLogger("largestack.prompt_templates")


class PromptTemplateError(Exception):
    """Raised on template registration / render errors."""


class _SafeFormatter(string.Formatter):
    """A string.Formatter that fails loud on missing variables.

    Default Python format() raises KeyError silently (or worse, lets the
    template be rendered with the missing field still present). We force
    explicit failure so missing placeholders don't slip through to LLMs.
    """

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            if key not in kwargs:
                raise PromptTemplateError(f"missing variable for placeholder {{{key}}}")
            return kwargs[key]
        return super().get_value(key, args, kwargs)


_formatter = _SafeFormatter()


class PromptRegistry:
    """In-memory + optional JSON-backed registry of versioned prompt templates."""

    def __init__(self, persist_path: str | None = None):
        """
        Args:
            persist_path: Optional path to a JSON file. When set, register/
                set_active calls are persisted, and __init__ loads existing
                templates from disk.
        """
        # name -> { version -> template_text }
        self._templates: dict[str, dict[str, str]] = {}
        # name -> active_version
        self._active: dict[str, str] = {}
        # name -> Counter[version] for usage analytics
        self._counters: dict[str, Counter[str]] = {}
        self._lock = Lock()
        self.persist_path = persist_path
        if persist_path:
            self._load()

    # -------------------- registration --------------------

    def register(self, name: str, template: str, version: str = "v1") -> None:
        """Register (or update) a template at the given version.

        If this is the first version for ``name``, it becomes active by default.
        """
        if not name or not isinstance(name, str):
            raise PromptTemplateError("name must be a non-empty string")
        if not isinstance(template, str):
            raise PromptTemplateError("template must be a string")
        if not version or not isinstance(version, str):
            raise PromptTemplateError("version must be a non-empty string")

        with self._lock:
            versions = self._templates.setdefault(name, {})
            versions[version] = template
            if name not in self._active:
                self._active[name] = version
            self._counters.setdefault(name, Counter())
        if self.persist_path:
            self._save()

    def set_active(self, name: str, version: str) -> None:
        """Promote a registered version to be the default for ``name``."""
        with self._lock:
            if name not in self._templates:
                raise PromptTemplateError(f"unknown template {name!r}")
            if version not in self._templates[name]:
                raise PromptTemplateError(f"version {version!r} not registered for {name!r}")
            self._active[name] = version
        if self.persist_path:
            self._save()

    def get_active(self, name: str) -> str:
        """Return the currently-active version of ``name``."""
        with self._lock:
            if name not in self._active:
                raise PromptTemplateError(f"unknown template {name!r}")
            return self._active[name]

    def list_versions(self, name: str) -> list[str]:
        with self._lock:
            return sorted(self._templates.get(name, {}).keys())

    def list_templates(self) -> list[str]:
        with self._lock:
            return sorted(self._templates.keys())

    # -------------------- rendering --------------------

    def render(self, _name: str, _version: str | None = None, **vars) -> str:
        """Render a template by name, optionally pinning to a specific version.

        Note: positional-only ``_name`` and ``_version`` use a leading
        underscore so user variable dicts can include keys like ``name``
        or ``version`` without colliding.

        ``_version=None`` means "use the active version".

        Raises ``PromptTemplateError`` if the template or version is unknown,
        or if any placeholder is missing in ``vars``.
        """
        name, version = _name, _version
        with self._lock:
            if name not in self._templates:
                raise PromptTemplateError(f"unknown template {name!r}")
            v = version or self._active[name]
            if v not in self._templates[name]:
                raise PromptTemplateError(f"version {v!r} not registered for {name!r}")
            tmpl = self._templates[name][v]
            self._counters[name][v] += 1

        try:
            return _formatter.format(tmpl, **vars)
        except PromptTemplateError:
            raise
        except (KeyError, IndexError, ValueError) as e:
            raise PromptTemplateError(f"render error for {name}@{v}: {e}") from e

    def render_with_split(
        self,
        _name: str,
        split: dict[str, int],
        rng: random.Random | None = None,
        **vars,
    ) -> tuple[str, str]:
        """Pick one of the versions weighted by ``split`` and render it.

        Args:
            _name: template name (positional-only, leading underscore so
                variables named ``name`` don't collide).
            split: ``{version: weight}``. Weights are summed; each version's
                probability = weight / sum.
            rng: optional Random for deterministic testing.

        Returns:
            ``(rendered_text, version_used)`` so the caller can log which
            version was actually shown to the user.
        """
        name = _name
        if not split:
            raise PromptTemplateError("split must be non-empty")
        rng = rng or random.Random()
        with self._lock:
            if name not in self._templates:
                raise PromptTemplateError(f"unknown template {name!r}")
            available = self._templates[name]
            for v in split:
                if v not in available:
                    raise PromptTemplateError(f"version {v!r} not registered for {name!r}")
        total = sum(split.values())
        if total <= 0:
            raise PromptTemplateError("split weights must sum to > 0")
        r = rng.uniform(0, total)
        cumulative = 0.0
        chosen: str | None = None
        for v, w in split.items():
            cumulative += w
            if r <= cumulative:
                chosen = v
                break
        if chosen is None:  # numerical edge
            chosen = list(split.keys())[-1]
        text = self.render(name, chosen, **vars)
        return text, chosen

    # -------------------- analytics --------------------

    def usage_counts(self, name: str) -> dict[str, int]:
        """Return ``{version: render_count}`` for ``name``."""
        with self._lock:
            return dict(self._counters.get(name, Counter()))

    # -------------------- persistence --------------------

    def _load(self) -> None:
        try:
            with open(self.persist_path) as f:
                data = json.load(f)
            self._templates = data.get("templates", {})
            self._active = data.get("active", {})
            for name in self._templates:
                self._counters.setdefault(name, Counter())
            log.info(f"PromptRegistry loaded {len(self._templates)} templates")
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning(f"PromptRegistry load failed: {e}")

    def _save(self) -> None:
        try:
            payload = {
                "templates": self._templates,
                "active": self._active,
                "saved_at": time.time(),
            }
            tmp = f"{self.persist_path}.tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f, indent=2)
            import os

            os.replace(tmp, self.persist_path)
        except Exception as e:
            log.warning(f"PromptRegistry save failed: {e}")
