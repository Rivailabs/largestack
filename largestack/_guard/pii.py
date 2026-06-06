"""PII detection and redaction."""
from __future__ import annotations
import logging
import os
import re
from largestack._guard.config import get_guardrail_config
from largestack._guard.policy import GuardrailAction, GuardrailMode
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.guard.pii")

PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(?<!\d)(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}(?!\d)"),
    "phone_in": re.compile(r"\b(?:\+?91[-\s]?)?[6-9]\d{9}\b"),  # Indian mobile
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "ip": re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"),
    # Indian identifiers
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "gstin": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b"),
    "ifsc": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    "upi": re.compile(r"\b[a-zA-Z0-9._-]+@[a-zA-Z]{3,}\b"),
}

SECRET_PATTERNS = {
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "generic_api_key": re.compile(r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-./+=]{12,}['\"]?", re.I),
}

FINANCIAL_PATTERNS = {
    "bank_account": re.compile(r"\b(?:account|acct)\s*(?:number|no\.?)?\s*[:#-]?\s*\d{9,18}\b", re.I),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    "card_context": re.compile(r"\b(?:card|debit|credit)\s*(?:number|no\.?)?\s*[:#-]?\s*(?:\d{4}[-\s]?){3}\d{4}\b", re.I),
}

EXTERNAL_LEAK_PATTERN = re.compile(
    r"\b(send|upload|post|forward|leak|exfiltrate)\b.{0,100}"
    r"\b(customer|pii|pan|aadhaar|card|bank|account|secret|token|api\s*key)\b.{0,120}"
    r"\bhttps?://",
    re.I,
)

class PIIGuard:
    def __init__(self, entities: list[str]|None=None, action: str = "redact"):
        self.entities = entities or list(PATTERNS.keys()); self.action = action
        self._presidio = None
        presidio_enabled = os.environ.get("LARGESTACK_ENABLE_PRESIDIO_PII", "").lower() in ("1", "true", "yes")
        if presidio_enabled:
            try:
                from presidio_analyzer import AnalyzerEngine
                self._presidio = AnalyzerEngine()
            except ImportError:
                pass

    async def check_input(self, messages):
        """Check input messages for PII. Block, redact, or warn."""
        cfg = get_guardrail_config()
        for m in messages:
            c = m.get("content", "")
            if isinstance(c, str):
                if self._detect_external_leak(c):
                    raise GuardrailBlockedError("sensitive_data", "External sensitive-data leakage detected")
                if cfg.mode == GuardrailMode.OBSERVE:
                    if self._detect_any(c) or self._detect_secret(c) or self._detect_financial(c):
                        log.warning("Sensitive data detected in input (mode=observe, not blocking)")
                    continue
                if self._detect_secret(c):
                    m["content"] = self.redact_secrets(c)
                    log.warning("Secret detected in input and redacted")
                    c = m["content"]
                if cfg.mode == GuardrailMode.STRICT or cfg.context == "bfsi":
                    if self._detect_financial(c):
                        c = self.redact_financial(c)
                    if self._detect_any(c):
                        c = self.redact(c)
                    m["content"] = c
                    if self._detect_any(str(m.get("content", ""))) or self._detect_financial(str(m.get("content", ""))):
                        log.warning("Sensitive data redacted/audited in strict mode")
                    continue
                if self.action == "block":
                    self._check_and_block(c)
                elif self.action == "redact":
                    m["content"] = self.redact_financial(self.redact(c))  # MUTATE in place
                elif self.action == "warn":
                    if self._detect_any(c) or self._detect_financial(c):
                        log.warning("PII detected in input (action=warn, not blocking)")
                        if cfg.pii_action == GuardrailAction.REDACT:
                            m["content"] = self.redact_financial(self.redact(c))

    async def check_output(self, response):
        """Check output for PII. Block, redact, or warn."""
        cfg = get_guardrail_config()
        if hasattr(response, "content") and isinstance(response.content, str):
            if cfg.mode == GuardrailMode.OBSERVE:
                if self._detect_any(response.content) or self._detect_secret(response.content) or self._detect_financial(response.content):
                    log.warning("Sensitive data detected in output (mode=observe, not blocking)")
                return
            if self._detect_secret(response.content):
                response.content = self.redact_secrets(response.content)
                log.warning("Secret detected in output and redacted")
            if cfg.mode == GuardrailMode.STRICT or cfg.context == "bfsi":
                response.content = self.redact_financial(self.redact(response.content))
                log.warning("Sensitive data redacted/audited in strict mode")
                return
            if self.action == "block":
                self._check_and_block(response.content)
            elif self.action == "redact":
                response.content = self.redact_financial(self.redact(response.content))
            elif self.action == "warn":
                if self._detect_any(response.content) or self._detect_financial(response.content):
                    log.warning("PII detected in output (action=warn, not blocking)")
                    if cfg.pii_action == GuardrailAction.REDACT:
                        response.content = self.redact_financial(self.redact(response.content))

    def _detect_any(self, text: str) -> bool:
        """Return True if any PII detected (without raising)."""
        if self._presidio:
            try:
                return bool(self._presidio.analyze(text=text, language="en"))
            except Exception:
                pass
        for et, pat in PATTERNS.items():
            if et in self.entities and pat.search(text):
                return True
        return False

    def _detect_secret(self, text: str) -> bool:
        return any(pat.search(text) for pat in SECRET_PATTERNS.values())

    def _detect_financial(self, text: str) -> bool:
        return any(pat.search(text) for pat in FINANCIAL_PATTERNS.values())

    def _detect_external_leak(self, text: str) -> bool:
        return bool(EXTERNAL_LEAK_PATTERN.search(text))

    def _check_and_block(self, text: str):
        """Raise if PII found (block mode)."""
        if self._presidio:
            results = self._presidio.analyze(text=text, language="en")
            if results:
                raise GuardrailBlockedError("pii", f"PII detected: {[r.entity_type for r in results]}")
            return
        for et, pat in PATTERNS.items():
            if et in self.entities and pat.search(text):
                raise GuardrailBlockedError("pii", f"PII detected: {et}")

    def redact(self, text: str) -> str:
        """Replace PII with [TYPE_REDACTED] placeholders."""
        if self._presidio:
            try:
                from presidio_anonymizer import AnonymizerEngine
                results = self._presidio.analyze(text=text, language="en")
                text = AnonymizerEngine().anonymize(
                    text=text, analyzer_results=results
                ).text
            except ImportError:
                pass
            except Exception as exc:
                log.warning("Presidio anonymization failed; falling back to regex PII redaction: %s", exc)
        # Defense in depth: run local regexes even after Presidio. Presidio may miss
        # SSN-style values, India-specific identifiers, or project-specific patterns.
        for et, pat in PATTERNS.items():
            if et in self.entities:
                text = pat.sub(f"[{et.upper()}_REDACTED]", text)
        # v1.1.1: context-gated separator-free SSN (e.g. "SSN: 123456789"). The
        # main `ssn` pattern only matches the dashed form; a bare 9-digit pattern
        # would over-match, so we require an SSN/social-security context word and
        # redact only the digits.
        if "ssn" in self.entities:
            text = re.sub(
                r"(?i)\b(ssn|social\s*security)(\s*(?:number|no\.?|#)?\s*[:#=-]?\s*)(?<!\d)\d{9}(?!\d)",
                lambda m: f"{m.group(1)}{m.group(2)}[SSN_REDACTED]", text)
        text = self.redact_secrets(text)
        return text

    def redact_secrets(self, text: str) -> str:
        """Replace secret/API-key/token-like values with placeholders."""
        for et, pat in SECRET_PATTERNS.items():
            text = pat.sub(f"[{et.upper()}_REDACTED]", text)
        return text

    def redact_financial(self, text: str) -> str:
        """Replace financial account/card-like values with placeholders."""
        for et, pat in FINANCIAL_PATTERNS.items():
            text = pat.sub(f"[{et.upper()}_REDACTED]", text)
        return text
