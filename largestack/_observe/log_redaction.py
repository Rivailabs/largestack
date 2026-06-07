"""Logging redaction filter — strips API keys and credentials from log records.

v0.3.7: prevents accidental key leakage via `log.debug(...)` payloads.

Install once at process startup:

    import logging
    from largestack._observe.log_redaction import install_redaction_filter
    install_redaction_filter()  # adds filter to root logger

The filter is conservative — it only redacts known patterns. False negatives
(missed leaks) are possible; false positives are unlikely.
"""

from __future__ import annotations
import logging
import re

# Patterns that almost certainly indicate a secret. Order matters — longer
# matches first so they don't get clobbered by shorter regexes.
_SECRET_PATTERNS = [
    # Anthropic
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{30,}"), "[REDACTED:anthropic_key]"),
    # OpenAI / DeepSeek / Together / Groq / Fireworks / Anyscale
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "[REDACTED:api_key]"),
    # Google / Gemini (AIza...) — we ship a Gemini provider, so cover its key shape
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "[REDACTED:google_key]"),
    # GitHub
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "[REDACTED:github_pat]"),
    (re.compile(r"gho_[A-Za-z0-9]{36,}"), "[REDACTED:github_token]"),
    # Slack
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED:slack_token]"),
    # AWS access key
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_access_key]"),
    # Bearer tokens (HTTP header form)
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{20,}"), "Bearer [REDACTED]"),
    # JWT (rough — three b64url segments separated by dots, last is signature)
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
        "[REDACTED:jwt]",
    ),
]


def _redact_text(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    for pat, repl in _SECRET_PATTERNS:
        s = pat.sub(repl, s)
    return s


class RedactionFilter(logging.Filter):
    """Filter that redacts secrets from LogRecord.msg and args.

    Returns True (keep record) always; mutation is the side effect.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact in main message
        if isinstance(record.msg, str):
            record.msg = _redact_text(record.msg)
        # Redact in args (used for %-formatted log messages)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact_text(v) if isinstance(v, str) else v for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_text(v) if isinstance(v, str) else v for v in record.args
                )
        return True


def install_redaction_filter(logger_name: str | None = None) -> RedactionFilter:
    """Install the redaction filter on a logger (default: root).

    Returns the installed filter so callers can remove it later if desired.
    Idempotent — installing twice on the same logger has no extra effect.
    """
    target = logging.getLogger(logger_name) if logger_name else logging.getLogger()
    # Check if already installed (avoid duplicate filters)
    for existing in target.filters:
        if isinstance(existing, RedactionFilter):
            return existing
    f = RedactionFilter()
    target.addFilter(f)
    return f
