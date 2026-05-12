# Recipe 03 — Hindi Aadhaar Redaction

**Use case:** A customer support chat in Hindi (Devanagari) leaks an
Aadhaar number. Redact PII **before** the message hits logs, vector
stores, or LLM prompts.

**DPDP:** §6 (data minimization), §7 (security safeguards).

## Why this is unique to LARGESTACK

No other open-source agent framework redacts PII written in
Devanagari, Bengali, Tamil, Telugu, or Indic numerals (०-९, ০-৯).
Tesseract + regex on Latin digits **misses** Devanagari numerals
entirely.

## Devanagari numeral mapping

| Latin | ० | १ | २ | ३ | ४ | ५ | ६ | ७ | ८ | ९ |
|---|---|---|---|---|---|---|---|---|---|---|
| **English** | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |

A Hindi user might write their Aadhaar as "१२३४ ५६७८ ९०१२" — looks
like text to a regex, but it's a 12-digit Aadhaar.

## Full code

```python
import asyncio
from largestack._indic import (
    normalize_indic_numerals,
    detect_script,
    redact_indic_pii,
)
from largestack._memory.long_term import LongTermMemoryManager

async def safe_log_user_message(
    message: str,
    *,
    tenant_id: str,
    user_id: str,
):
    # 1) Detect script (devanagari/tamil/telugu/...)
    script = detect_script(message)
    print(f"detected: {script}")

    # 2) Redact PII (Aadhaar, PAN, phone, email) — handles Indic numerals
    redacted = redact_indic_pii(message)

    # 3) Store the REDACTED form in conversation memory
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id=user_id,
    )
    await memory.add_recall(
        redacted,
        source="customer_chat",
        purpose="customer_support_history",
        lawful_basis="consent",
        ttl_seconds=30 * 24 * 3600,
    )
    return redacted


# Demo
async def main():
    # Hindi user shares Aadhaar in Devanagari numerals
    msg = "मेरा आधार नंबर १२३४ ५६७८ ९०१२ है"
    redacted = await safe_log_user_message(
        msg, tenant_id="t1", user_id="u1",
    )
    print(f"original:  {msg}")
    print(f"redacted:  {redacted}")
    # Output: मेरा आधार नंबर [REDACTED_AADHAAR] है

asyncio.run(main())
```

## Supported scripts

LARGESTACK Indic NLP handles 9 scripts: Devanagari (Hindi/Marathi/Sanskrit),
Bengali, Tamil, Telugu, Kannada, Malayalam, Gujarati, Punjabi
(Gurmukhi), Odia. The `redact_indic_pii` function normalises
script-specific numerals and applies all PII patterns.

## What gets redacted

| Pattern | Example | Replaced with |
|---|---|---|
| 12-digit Aadhaar | `1234 5678 9012` or `१२३४ ५६७८ ९०१२` | `[REDACTED_AADHAAR]` |
| PAN | `AAACR1234C` | `[REDACTED_PAN]` |
| Indian mobile | `+91 98765 43210` | `[REDACTED_PHONE]` |
| Email | `user@example.com` | `[REDACTED_EMAIL]` |
| Bank account (10–18 digits) | `123456789012` | `[REDACTED_ACCOUNT]` |

## Why this matters

- **Logs are forever**: redacting before logs prevents PII showing up in OpenSearch / CloudWatch / Datadog forever
- **Vector stores embed PII**: a non-redacted Aadhaar in a Pinecone index leaks across customers
- **LLM training**: redacted data → safe to use for fine-tuning
