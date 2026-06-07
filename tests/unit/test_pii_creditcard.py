"""Credit-card numbers must be FULLY redacted — not partially consumed by the phone
regex (regression for the leak where '4111111111111111' -> '[PHONE_REDACTED]111111').
"""

from __future__ import annotations

import re

from largestack._guard.pii import PIIGuard


def test_credit_card_fully_redacted_no_digit_leak():
    out = PIIGuard(action="redact").redact("my card is 4111111111111111 thanks")
    assert not re.search(r"\d{6,}", out), f"card digits leaked: {out!r}"


def test_credit_card_with_spaces_redacted():
    out = PIIGuard(action="redact").redact("card 4111 1111 1111 1111")
    assert not re.search(r"\d{4}[ -]?\d{4}", out), f"card leaked: {out!r}"


def test_real_phone_still_redacted():
    out = PIIGuard(action="redact").redact("call me at 555-123-4567 today")
    assert "PHONE_REDACTED" in out
    assert "555-123-4567" not in out
