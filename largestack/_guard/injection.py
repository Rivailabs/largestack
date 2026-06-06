"""Prompt injection detection — multi-pattern with sensitivity levels."""
from __future__ import annotations
import logging
import re
from largestack._guard.config import get_guardrail_config
from largestack._guard.policy import (
    GuardrailAction,
    GuardrailDecision,
    GuardrailMode,
    GuardrailRiskType,
    GuardrailSeverity,
    allow,
    block,
    isolate,
    warn,
)
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.guard.injection")

# Organized by category for clarity
JAILBREAK_PATTERNS = [
    r"ignore\s+(previous|all|above|prior|any)\s+(instructions|prompts|rules|guidelines)",
    r"ignore\s+all\s+previous\s+(instructions|prompts|rules|guidelines)",
    r"disregard\s+(your|the|all|any)\s+(instructions|rules|guidelines|programming)",
    r"forget\s+(everything|your|all|any)\s+(instructions|rules|training|guidelines)",
    r"you\s+are\s+now\s+",
    r"pretend\s+(you|to)\s+(are|be)\s+",
    r"act\s+as\s+(if|though)\s+you\s+(have|are|were)",
    r"override\s+(your|the|all|any)\s+(instructions|rules|programming)",
    r"new\s+(instructions|rules|persona|identity)\s*:",
    r"from\s+now\s+on\s+you\s+(are|will|must|should)",
]

SYSTEM_PROMPT_PATTERNS = [
    r"system\s*prompt",
    r"reveal\s+(your|the)\s+(system|initial|original)\s+(prompt|instructions)",
    r"what\s+(are|is)\s+your\s+(system|initial|original)\s+(prompt|instructions)",
    r"show\s+(me\s+)?(your|the)\s+(system|original)\s+(prompt|instructions)",
    r"repeat\s+(your|the)\s+(system|initial)\s+(prompt|message)",
]

FORMAT_INJECTION_PATTERNS = [
    r"\[INST\]", r"<\|im_start\|>", r"<\|system\|>",
    r"###\s*(System|Instruction|Human|Assistant)\s*:",
    r"\bSYSTEM\s*:",
    r"\bSYSTEM\s*:\s*new\s+instructions\s+override",
    r"```system", r"<system>",
    r"ADMIN\s*:", r"DEVELOPER\s*:",
]

MANIPULATION_PATTERNS = [
    r"do\s+anything\s+now",
    r"you\s+have\s+no\s+(restrictions|limits|rules|boundaries)",
    r"jailbreak", r"DAN\s+mode",
    r"developer\s+mode\s+(enabled|activated|on)",
    r"bypass\s+(your|the|all)\s+(filters|safety|restrictions|rules)",
    r"unlock\s+(your|all)\s+(capabilities|potential|restrictions)",
    # v1.1.1: high-signal, low-FP addition — qualified so benign "unfiltered coffee",
    # "no filter on the camera", "no limits on creativity" do NOT match. (Broader
    # "no filters/guardrails" / "with no limits" variants were tried and dropped:
    # they false-positived on ordinary text. The opt-in ML guard covers the rest.)
    r"unfiltered\s+(model|ai|assistant|version|mode|chatbot|response)",
]

ALL_PATTERNS = [re.compile(p, re.I) for p in
    JAILBREAK_PATTERNS + SYSTEM_PROMPT_PATTERNS +
    FORMAT_INJECTION_PATTERNS + MANIPULATION_PATTERNS]

# v1.1.1: high-confidence patterns — a SINGLE match here blocks in PROTECT mode
# (default), closing the gap where common single-pattern jailbreaks were only warned.
# IMPORTANT: this is the UNAMBIGUOUS-attack subset only. The ambiguous roleplay
# patterns ("you are now", "pretend you are", "act as if", "from now on you") are
# EXCLUDED because they have legitimate uses ("pretend you are a tutor", "you are now
# connected") and single-match-blocking them caused false positives; those still need
# >=2 patterns to block. Format tokens are also excluded (legit in code/markdown).
# Still gated to NOT fire in rag/document/planning context.
_STRONG_JAILBREAK = [
    # verb + (intervening adjectives) + target within one clause: catches
    # "ignore all prior instructions", "disregard your earlier rules", etc.
    r"\b(ignore|disregard|forget|override)\b[\w\s,'-]{0,40}\b(instruction|instructions|prompt|prompts|rule|rules|guideline|guidelines|programming)\b",
    r"new\s+(instructions|rules|persona|identity)\s*:",
]
HIGH_CONFIDENCE_PATTERNS = [re.compile(p, re.I) for p in
    _STRONG_JAILBREAK + SYSTEM_PROMPT_PATTERNS + MANIPULATION_PATTERNS]

# Strong proximity patterns must also count toward detection (is_injection), so a bare
# "ignore all prior instructions" (no other trigger) is caught, not silently allowed.
ALL_PATTERNS = ALL_PATTERNS + [re.compile(p, re.I) for p in _STRONG_JAILBREAK]

EXTERNAL_EXFILTRATION_PATTERNS = [
    re.compile(r"\b(exfiltrat\w*|leak\w*)\b.{0,80}\b(api\s*keys?|secrets?|tokens?|passwords?|credentials?)\b", re.I),
    re.compile(r"\b(send|upload|post|forward)\b.{0,80}\b(api\s*keys?|secrets?|tokens?|passwords?|credentials?)\b.{0,100}\b(external|unapproved|evil|attacker|unknown)\b", re.I),
    re.compile(r"\b(api\s*keys?|secrets?|tokens?|passwords?|credentials?)\b.{0,80}\b(to|into|via)\b.{0,80}\bhttps?://", re.I),
    re.compile(r"\b(exfiltrat\w*|leak\w*)\b.{0,80}\b(customer\s+data|pii|aadhaar|pan|card\s+data)\b", re.I),
    re.compile(r"\bhttps?://\S*(evil|exfil|pastebin|requestbin)\S*", re.I),
]

CREDENTIAL_THEFT_PATTERNS = [
    re.compile(r"\b(steal|dump|extract|harvest|exfiltrate)\b.{0,80}\b(browser\s+tokens?|session\s+cookies?|oauth\s+tokens?|credentials?|passwords?|api\s*keys?)\b", re.I),
    re.compile(r"\bbypass\b.{0,40}\b(login|auth|authentication|mfa|2fa|access\s+control)\b", re.I),
]

MALWARE_PATTERNS = [
    re.compile(r"\b(build|create|write|generate)\b.{0,80}\b(malware|ransomware|trojan|keylogger|worm|botnet)\b", re.I),
    re.compile(r"\bmalware\b.{0,80}\b(exfiltrate|steal|credentials?|tokens?|keys?)\b", re.I),
]

ILLEGAL_ABUSE_PATTERNS = [
    re.compile(r"\b(illegal|fraud|phishing|carding|money\s+laundering)\b.{0,80}\b(workflow|scheme|operation|automation|playbook)\b", re.I),
]

SECRET_BYPASS_PATTERNS = [
    re.compile(r"\b(ignore|override|disregard)\b.{0,80}\b(policy|safety|auth|authorization|permissions?)\b", re.I),
    re.compile(r"\bbypass\b.{0,80}\b(auth|authorization|permissions?)\b", re.I),
    re.compile(r"\b(reveal|print|show|leak)\b.{0,80}\b(api\s*keys?|secrets?|tokens?|passwords?|credentials?)\b", re.I),
]


class InjectionGuard:
    """Detect prompt injection attempts.
    
    Sensitivity levels:
      - high: any 1 pattern match triggers
      - medium: 2+ pattern matches (default, reduces false positives)
      - low: 3+ pattern matches
    """
    def __init__(self, sensitivity: str = "medium"):
        self.sensitivity = sensitivity
        self._violation_count = 0
    
    async def check_input(self, messages):
        for m in messages:
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, str):
                    decision = self.evaluate(c)
                    if decision.action != GuardrailAction.ALLOW:
                        self._violation_count += 1
                        log.warning(
                            "Prompt guard decision: action=%s risk=%s severity=%s message=%s",
                            decision.action.value,
                            decision.risk_type.value,
                            decision.severity.value,
                            decision.message,
                        )
                    if not decision.allowed:
                        raise GuardrailBlockedError("injection", decision.message)
    
    async def check_output(self, response):
        pass
    
    def _detect(self, text: str) -> bool:
        if not text:
            return False
        score = sum(1 for p in ALL_PATTERNS if p.search(text))
        threshold = {"low": 3, "medium": 1, "high": 1}.get(self.sensitivity, 1)
        return score >= threshold

    def evaluate(self, text: str) -> GuardrailDecision:
        """Return a risk-aware decision for prompt injection and abuse text."""
        cfg = get_guardrail_config()
        is_injection = self._detect(text)
        critical = self._critical_risk(text)

        if cfg.mode == GuardrailMode.OBSERVE:
            if is_injection or critical:
                return warn(
                    "Guardrail observe mode: risk logged only",
                    risk_type=critical or GuardrailRiskType.PROMPT_INJECTION,
                    severity=GuardrailSeverity.HIGH if critical else GuardrailSeverity.MEDIUM,
                )
            return self._allow_decision()

        if critical:
            if (
                critical == GuardrailRiskType.EXTERNAL_EXFILTRATION
                and cfg.context in {"planning", "benchmark"}
                and not self._has_explicit_malicious_destination(text)
                and (
                    not re.search(r"\b(exfiltrate|leak)\b", text, re.I)
                    or self._is_defensive_planning_context(text)
                )
            ):
                return warn(
                    "External data movement risk discussed in planning context",
                    risk_type=critical,
                    severity=GuardrailSeverity.HIGH,
                    metadata={"context": cfg.context},
                )
            if cfg.mode == GuardrailMode.WARN and cfg.critical_risk_action != GuardrailAction.BLOCK:
                return warn(
                    "Critical abuse risk detected",
                    risk_type=critical,
                    severity=GuardrailSeverity.CRITICAL,
                )
            return block(
                "Critical abuse risk detected",
                risk_type=critical,
                severity=GuardrailSeverity.CRITICAL,
            )

        if not is_injection:
            return self._allow_decision()

        context = cfg.context
        planning_context = context in {"planning", "benchmark", "rag", "document", "documents"}
        if cfg.mode == GuardrailMode.WARN or planning_context:
            return warn(
                "Prompt injection pattern detected; continuing with warning",
                risk_type=GuardrailRiskType.PROMPT_INJECTION,
                severity=GuardrailSeverity.MEDIUM,
                metadata={"context": context},
            )

        if cfg.mode == GuardrailMode.STRICT:
            return isolate(
                "Prompt injection pattern detected; isolate untrusted content",
                risk_type=GuardrailRiskType.PROMPT_INJECTION,
                severity=GuardrailSeverity.HIGH,
                metadata={"context": context, "audit": True},
            )

        if cfg.mode == GuardrailMode.PROTECT and (
            self._pattern_score(text) >= 2 or self._high_confidence(text)
        ):
            return block(
                "High-confidence prompt injection detected",
                risk_type=GuardrailRiskType.PROMPT_INJECTION,
                severity=GuardrailSeverity.HIGH,
                metadata={"context": context},
            )

        if cfg.prompt_injection_action == GuardrailAction.BLOCK:
            return block(
                "Prompt injection detected",
                risk_type=GuardrailRiskType.PROMPT_INJECTION,
                severity=GuardrailSeverity.HIGH,
            )
        if cfg.prompt_injection_action == GuardrailAction.ISOLATE:
            return isolate(
                "Prompt injection pattern detected; isolate untrusted content",
                risk_type=GuardrailRiskType.PROMPT_INJECTION,
                severity=GuardrailSeverity.MEDIUM,
                metadata={"context": context},
            )
        return warn(
            "Prompt injection pattern detected; continuing with warning",
            risk_type=GuardrailRiskType.PROMPT_INJECTION,
            severity=GuardrailSeverity.MEDIUM,
            metadata={"context": context},
        )

    @staticmethod
    def _allow_decision() -> GuardrailDecision:
        return allow(
            "No prompt injection detected",
            risk_type=GuardrailRiskType.PROMPT_INJECTION,
            severity=GuardrailSeverity.LOW,
        )

    @staticmethod
    def _pattern_score(text: str) -> int:
        return sum(1 for p in ALL_PATTERNS if p.search(text))

    @staticmethod
    def _high_confidence(text: str) -> bool:
        """A single high-confidence (jailbreak/system-prompt/manipulation) match."""
        return any(p.search(text) for p in HIGH_CONFIDENCE_PATTERNS)

    @staticmethod
    def _critical_risk(text: str) -> GuardrailRiskType | None:
        checks = (
            (MALWARE_PATTERNS, GuardrailRiskType.MALWARE),
            (CREDENTIAL_THEFT_PATTERNS, GuardrailRiskType.CREDENTIAL_THEFT),
            (EXTERNAL_EXFILTRATION_PATTERNS, GuardrailRiskType.EXTERNAL_EXFILTRATION),
            (ILLEGAL_ABUSE_PATTERNS, GuardrailRiskType.ILLEGAL_ABUSE),
            (SECRET_BYPASS_PATTERNS, GuardrailRiskType.CREDENTIAL_THEFT),
        )
        for patterns, risk_type in checks:
            if any(p.search(text) for p in patterns):
                return risk_type
        return None

    @staticmethod
    def _has_explicit_malicious_destination(text: str) -> bool:
        return bool(re.search(r"\bhttps?://\S*(evil|exfil|pastebin|requestbin)\S*", text, re.I))

    @staticmethod
    def _is_defensive_planning_context(text: str) -> bool:
        """True when exfiltration/secrets are discussed as controls, not instructions."""
        defensive_terms = (
            r"prevent",
            r"detect",
            r"block",
            r"redact",
            r"monitor",
            r"audit",
            r"mitigate",
            r"guard\s+against",
            r"protect",
            r"policy",
            r"control",
            r"dlp",
            r"data\s+loss\s+prevention",
            r"approved\s+provider",
            r"unapproved\s+provider",
            r"risk",
        )
        sensitive_terms = r"(exfiltrat\w*|leak\w*|api\s*keys?|secrets?|tokens?|passwords?|credentials?|customer\s+data|pii)"
        for term in defensive_terms:
            if re.search(rf"\b{term}\b.{{0,160}}\b{sensitive_terms}\b", text, re.I | re.S):
                return True
            if re.search(rf"\b{sensitive_terms}\b.{{0,160}}\b{term}\b", text, re.I | re.S):
                return True
        return False
    
    def analyze(self, text: str) -> dict:
        """Return detection details without raising."""
        matched = [p.pattern for p in ALL_PATTERNS if p.search(text)]
        return {
            "is_injection": len(matched) >= {"low": 3, "medium": 1, "high": 1}.get(self.sensitivity, 1),
            "matched_patterns": len(matched),
            "categories": {
                "jailbreak": sum(1 for p in JAILBREAK_PATTERNS if re.search(p, text, re.I)),
                "system_prompt": sum(1 for p in SYSTEM_PROMPT_PATTERNS if re.search(p, text, re.I)),
                "format_injection": sum(1 for p in FORMAT_INJECTION_PATTERNS if re.search(p, text, re.I)),
                "manipulation": sum(1 for p in MANIPULATION_PATTERNS if re.search(p, text, re.I)),
            }
        }
    
    @property
    def stats(self) -> dict:
        return {
            "sensitivity": self.sensitivity,
            "pattern_count": len(ALL_PATTERNS),
            "violation_count": self._violation_count,
        }

# Backward compatibility alias
PATTERNS = ALL_PATTERNS
