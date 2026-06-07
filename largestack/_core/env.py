"""Environment helpers: zero-dependency .env auto-loading + standard-key fallback.

Two first-run conveniences (both backward-compatible):
  * load_dotenv(): on `import largestack`, load a project .env into os.environ
    WITHOUT overriding already-set vars. Opt out with LARGESTACK_NO_DOTENV=1.
  * resolve_provider_key(): read LARGESTACK_<PROVIDER>_API_KEY first, then fall
    back to the provider's conventional env name (e.g. OPENAI_API_KEY) so a key
    a user already has set "just works".
"""
from __future__ import annotations

import os
from pathlib import Path

# largestack provider -> the conventional env var names that provider's own SDK uses.
# Checked only as a fallback when LARGESTACK_<PROVIDER>_API_KEY is unset.
STANDARD_KEY_ENV: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "google": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "cohere": ["COHERE_API_KEY", "CO_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "nvidia": ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "sambanova": ["SAMBANOVA_API_KEY"],
    "ai21": ["AI21_API_KEY"],
    "voyage": ["VOYAGE_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "databricks": ["DATABRICKS_TOKEN"],
    "anyscale": ["ANYSCALE_API_KEY"],
}


def resolve_provider_key(provider: str) -> str:
    """Return the API key for ``provider``: the LARGESTACK_-prefixed var wins, then
    the provider's conventional env name(s). Empty string if none set."""
    p = (provider or "").lower()
    v = os.environ.get(f"LARGESTACK_{p.upper()}_API_KEY", "")
    if v:
        return v
    for name in STANDARD_KEY_ENV.get(p, []):
        v = os.environ.get(name, "")
        if v:
            return v
    return ""


def _is_disabled() -> bool:
    return os.environ.get("LARGESTACK_NO_DOTENV", "").lower() in ("1", "true", "yes")


def _find_dotenv(start: Path, max_up: int = 4) -> Path | None:
    """Find the nearest .env from ``start`` walking up a few levels."""
    for d in [start, *list(start.parents)[:max_up]]:
        cand = d / ".env"
        if cand.is_file():
            return cand
    return None


def load_dotenv(path: str | os.PathLike | None = None, override: bool = False) -> int:
    """Load KEY=VALUE pairs from a .env file into os.environ. Returns the count set.

    - Does NOT override already-set environment variables (unless override=True) —
      so real shell/CI/Docker secrets always win over a committed-by-mistake .env.
    - No-op (returns 0) if LARGESTACK_NO_DOTENV is truthy or no .env is found.
    - Zero dependencies: minimal parser (handles comments, blank lines, `export `,
      and single/double quotes). Not a full dotenv spec — keep .env simple.
    """
    if _is_disabled():
        return 0
    p: Path | None = Path(path) if path else _find_dotenv(Path.cwd())
    if p is None or not p.is_file():
        return 0
    count = 0
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        if not key or not key.replace("_", "").isalnum():
            continue
        if override or key not in os.environ:
            os.environ[key] = val
            count += 1
    return count
