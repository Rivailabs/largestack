"""Eval framework extensions (v0.13.0).

Adds two missing pieces to ``largestack._eval``:

1. **Embedding similarity assertions** — cheaper than LLM-judge,
   handles paraphrases. Uses any ``EmbedderProtocol`` from
   ``largestack._memory.vector_store``.
2. **Dataset versioning** — every YAML eval suite is hashed; reports
   include the dataset hash so you can prove "this 92% pass-rate is
   against suite v3.4 (sha256: a3b1...)".

Backward compatible — existing suites work unchanged.
"""

from __future__ import annotations
import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("largestack.eval.v130")


# -------------------- Dataset versioning --------------------


@dataclass
class SuiteVersion:
    """Hashed identity of an eval suite. Embed in reports."""

    name: str
    sha256: str
    case_count: int
    file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "case_count": self.case_count,
            "file_path": self.file_path,
        }


def hash_suite_yaml(yaml_text: str) -> str:
    """Stable SHA-256 hash of an eval suite YAML.

    Strategy: parse YAML, re-emit canonically (sorted keys, no comments),
    then hash. This means whitespace / comment changes don't bump the
    hash, but content changes do.
    """
    try:
        import yaml
    except ImportError as e:
        raise ImportError("PyYAML required") from e

    parsed = yaml.safe_load(yaml_text)
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def version_suite(yaml_path: Path | str) -> SuiteVersion:
    """Compute a ``SuiteVersion`` from a YAML file."""
    p = Path(yaml_path)
    if not p.exists():
        raise FileNotFoundError(f"suite not found: {p}")

    text = p.read_text(encoding="utf-8")
    h = hash_suite_yaml(text)

    try:
        import yaml

        parsed = yaml.safe_load(text)
    except ImportError:
        parsed = {}

    name = (parsed or {}).get("name", p.stem) if isinstance(parsed, dict) else p.stem
    cases = (parsed or {}).get("cases", []) if isinstance(parsed, dict) else []

    return SuiteVersion(
        name=name,
        sha256=h,
        case_count=len(cases) if isinstance(cases, list) else 0,
        file_path=str(p.resolve()),
    )


def short_hash(sha256: str, length: int = 12) -> str:
    """Display-friendly short hash, e.g. 'a3b1c9d2e4f5'."""
    return sha256[:length]


# -------------------- Embedding similarity assertions --------------------


@dataclass
class EmbeddingSimilarityAssertion:
    """Assert that ``actual`` is semantically close to ``expected``.

    Cheaper than LLM-judge; handles paraphrases that substring can't.

    Args:
        expected: the reference text
        threshold: minimum cosine similarity to pass (0.0-1.0)
        embedder: any embedder; defaults to ``HashingEmbedder`` if absent
    """

    expected: str
    threshold: float = 0.7
    embedder: Any = None

    async def evaluate(self, actual: str) -> tuple[bool, float, str]:
        """Returns ``(passed, similarity, reason)``."""
        if not actual:
            return False, 0.0, "empty actual"
        if not self.expected:
            return False, 0.0, "empty expected"

        embedder = self.embedder
        if embedder is None:
            from largestack._memory.vector_store import HashingEmbedder

            embedder = HashingEmbedder()

        try:
            v_actual = await embedder.embed(actual)
            v_expected = await embedder.embed(self.expected)
        except Exception as e:
            return False, 0.0, f"embed failed: {e}"

        sim = _cosine(v_actual, v_expected)
        passed = sim >= self.threshold
        reason = f"sim={sim:.3f} {'>=' if passed else '<'} {self.threshold:.3f}"
        return passed, sim, reason


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# -------------------- Suite parsing for new assertion type --------------------


def parse_assertions(case_spec: dict[str, Any]) -> list[Any]:
    """Parse a YAML case's assertion specs into assertion objects.

    Supports:
    - ``contains: ["x", "y"]`` — substring (legacy)
    - ``equals: "exact"`` — exact match (legacy)
    - ``similarity: {expected: "...", threshold: 0.8}`` — NEW v0.13

    Returns a list of objects with an async ``.evaluate(actual)`` method.
    """
    assertions = []

    # Substring assertions (legacy)
    contains = case_spec.get("contains", [])
    if isinstance(contains, str):
        contains = [contains]
    for s in contains:
        assertions.append(_ContainsAssertion(s))

    # Equals assertion (legacy)
    if "equals" in case_spec:
        assertions.append(_EqualsAssertion(case_spec["equals"]))

    # Similarity assertion (NEW v0.13)
    sim_spec = case_spec.get("similarity")
    if isinstance(sim_spec, dict):
        assertions.append(
            EmbeddingSimilarityAssertion(
                expected=sim_spec["expected"],
                threshold=float(sim_spec.get("threshold", 0.7)),
            )
        )
    elif isinstance(sim_spec, str):
        # Shorthand: similarity: "expected text"
        assertions.append(EmbeddingSimilarityAssertion(expected=sim_spec))

    return assertions


@dataclass
class _ContainsAssertion:
    needle: str

    async def evaluate(self, actual: str) -> tuple[bool, float, str]:
        ok = self.needle.lower() in (actual or "").lower()
        return (
            ok,
            (1.0 if ok else 0.0),
            (f"contains '{self.needle}'" if ok else f"missing '{self.needle}'"),
        )


@dataclass
class _EqualsAssertion:
    expected: str

    async def evaluate(self, actual: str) -> tuple[bool, float, str]:
        ok = (actual or "").strip() == str(self.expected).strip()
        return ok, (1.0 if ok else 0.0), ("equals" if ok else "not equal")


# -------------------- Report enrichment --------------------


def enrich_report_with_version(
    report: dict[str, Any],
    version: SuiteVersion,
) -> dict[str, Any]:
    """Add suite-version info to a report dict (in place + return)."""
    report["suite_version"] = version.to_dict()
    report["suite_short_hash"] = short_hash(version.sha256)
    return report


__all__ = [
    "SuiteVersion",
    "hash_suite_yaml",
    "version_suite",
    "short_hash",
    "EmbeddingSimilarityAssertion",
    "parse_assertions",
    "enrich_report_with_version",
]
