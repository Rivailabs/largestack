"""Public Guardrails convenience API."""

from __future__ import annotations
from largestack._guard.pipeline import GuardrailPipeline
from largestack._guard.pii import PIIGuard
from largestack._guard.injection import InjectionGuard
from largestack._guard.hallucination import HallucinationGuard
from largestack._guard.toxicity import ToxicityGuard
from largestack._guard.topic import TopicGuard


def create_guardrails(
    pii: bool = True,
    injection: bool = True,
    hallucination: bool = False,
    toxicity: bool = False,
    topic_blocklist: list[str] = None,
    pii_action: str = "redact",
    injection_sensitivity: str = "medium",
) -> GuardrailPipeline:
    """Create a guardrail pipeline with common configurations."""
    guards = []
    if pii:
        guards.append(PIIGuard(action=pii_action))
    if injection:
        guards.append(InjectionGuard(sensitivity=injection_sensitivity))
    if hallucination:
        guards.append(HallucinationGuard())
    if toxicity:
        guards.append(ToxicityGuard())
    if topic_blocklist:
        guards.append(TopicGuard(blocklist=topic_blocklist))
    return GuardrailPipeline(guards)
