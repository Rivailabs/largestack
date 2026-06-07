"""Indic language NLP for LARGESTACK (v0.11.0).

LARGESTACK-unique capability: no global agent framework ships native Indic
language support. Closes the gap that LangChain / LlamaIndex / CrewAI
all leave open — they treat Hindi/Tamil/Telugu/Bengali text as opaque
UTF-8 byte sequences. LARGESTACK treats them as first-class.

Provides:

- ``script_detect(text)`` — detect Devanagari, Tamil, Telugu, Bengali, Latin
- ``IndicTokenizer`` — sentence + word tokenization for major Indic scripts
- Indic PII patterns:
    - Aadhaar in Devanagari numerals (``१२३४ ५६७८ ९०१२``)
    - Indian mobile numbers in multiple formats
    - Hindi name patterns
    - Indic addresses (PIN code detection)
- ``transliterate`` — basic Devanagari ↔ Latin transliteration

Zero external deps. Pure stdlib regex.
"""

from __future__ import annotations
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

log = logging.getLogger("largestack.indic")


# -------------------- Script detection --------------------

# Unicode block ranges for major Indic scripts
SCRIPT_RANGES = {
    "devanagari": (0x0900, 0x097F),  # Hindi, Marathi, Sanskrit, Konkani, Nepali
    "bengali": (0x0980, 0x09FF),  # Bengali, Assamese
    "gurmukhi": (0x0A00, 0x0A7F),  # Punjabi
    "gujarati": (0x0A80, 0x0AFF),
    "oriya": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
}


def script_detect(text: str) -> dict[str, float]:
    """Return fraction of characters in each Indic script + Latin.

    Returns dict like ``{"devanagari": 0.6, "latin": 0.3, "other": 0.1}``.
    """
    if not text:
        return {}

    counts: dict[str, int] = {"latin": 0, "other": 0}
    counts.update({k: 0 for k in SCRIPT_RANGES})
    total = 0

    for ch in text:
        if ch.isspace() or not ch.isprintable():
            continue
        total += 1
        cp = ord(ch)
        if 0x0041 <= cp <= 0x007A or 0x0061 <= cp <= 0x007A:  # ASCII letters
            counts["latin"] += 1
            continue
        matched = False
        for name, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[name] += 1
                matched = True
                break
        if not matched:
            counts["other"] += 1

    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items() if v > 0}


def primary_script(text: str) -> str:
    """Return the script with highest character count, or 'unknown'."""
    fractions = script_detect(text)
    if not fractions:
        return "unknown"
    return max(fractions, key=fractions.get)


# -------------------- Indic Tokenizer --------------------

# Sentence boundary markers for Indic scripts
# Devanagari Danda (।) and Double Danda (॥) are sentence ends in Hindi/Sanskrit
_INDIC_SENTENCE_END = re.compile(r"(?<=[।॥।.!?])\s+")
# Latin-style sentence boundaries
_LATIN_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")

# Word boundaries — Indic scripts use whitespace + punctuation
_WORD_SPLIT = re.compile(r"[\s।॥,\.\?!:;\(\)\[\]\"'/\\\-]+")


@dataclass
class IndicTokenizer:
    """Sentence + word tokenizer for Indic + Latin mixed text.

    Args:
        preserve_danda: keep ``।`` as a separate token (default False).
    """

    preserve_danda: bool = False

    def sentences(self, text: str) -> list[str]:
        """Split into sentences, handling Devanagari Danda + Latin punctuation."""
        if not text or not text.strip():
            return []
        # Split on either Indic or Latin sentence boundaries
        parts = _INDIC_SENTENCE_END.split(text.strip())
        out = []
        for p in parts:
            # Further split on Latin-style boundaries within each part
            sub = _LATIN_SENTENCE_END.split(p)
            out.extend(s.strip() for s in sub if s.strip())
        return out

    def words(self, text: str) -> list[str]:
        """Split into words. Strips punctuation."""
        if not text:
            return []
        words = _WORD_SPLIT.split(text)
        return [w for w in words if w]


# -------------------- Indic PII Patterns --------------------

# Devanagari digit map
DEVANAGARI_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}
DEVANAGARI_DIGITS_REV = {v: k for k, v in DEVANAGARI_DIGITS.items()}

# Bengali digit map
BENGALI_DIGITS = {
    "০": "0",
    "১": "1",
    "২": "2",
    "৩": "3",
    "৪": "4",
    "৫": "5",
    "৬": "6",
    "৭": "7",
    "৮": "8",
    "৯": "9",
}

# Tamil digit map
TAMIL_DIGITS = {
    "௦": "0",
    "௧": "1",
    "௨": "2",
    "௩": "3",
    "௪": "4",
    "௫": "5",
    "௬": "6",
    "௭": "7",
    "௮": "8",
    "௯": "9",
}

# Telugu digit map
TELUGU_DIGITS = {
    "౦": "0",
    "౧": "1",
    "౨": "2",
    "౩": "3",
    "౪": "4",
    "౫": "5",
    "౬": "6",
    "౭": "7",
    "౮": "8",
    "౯": "9",
}


def normalize_indic_digits(text: str) -> str:
    """Convert Indic numerals to ASCII digits."""
    if not text:
        return text
    # Combine all digit maps
    all_maps: dict[str, str] = {}
    all_maps.update(DEVANAGARI_DIGITS)
    all_maps.update(BENGALI_DIGITS)
    all_maps.update(TAMIL_DIGITS)
    all_maps.update(TELUGU_DIGITS)
    return "".join(all_maps.get(ch, ch) for ch in text)


# Aadhaar in Devanagari numerals
AADHAAR_DEVANAGARI = re.compile(r"[२-९][०-९]{3}\s?[०-९]{4}\s?[०-९]{4}")

# Aadhaar in Bengali numerals
AADHAAR_BENGALI = re.compile(r"[২-৯][০-৯]{3}\s?[০-৯]{4}\s?[০-৯]{4}")

# Aadhaar in Tamil numerals (rare but possible)
AADHAAR_TAMIL = re.compile(r"[௨-௯][௦-௯]{3}\s?[௦-௯]{4}\s?[௦-௯]{4}")

# Indian mobile in multiple formats: +91-9876543210, 09876543210, 9876543210
INDIAN_MOBILE = re.compile(r"(?:\+91[-\s]?|0)?[6-9][0-9]{9}\b")

# Indian PIN code (6 digits)
PIN_CODE = re.compile(r"\b[1-9][0-9]{5}\b")

# Indian PIN code in Devanagari numerals
PIN_CODE_DEVANAGARI = re.compile(r"[१-९][०-९]{5}")

# Common Hindi name particles (for entity hint, not strict matching)
# These appear in addresses and Hindi-script PII contexts
HINDI_HONORIFIC_PARTICLES = re.compile(r"(?:श्री|श्रीमती|डॉ|कुमारी|पंडित|मौलाना)\s*\.?\s*")


def detect_indic_pii(text: str) -> dict[str, list[dict]]:
    """Scan text for Indic-script PII. Returns matches per type."""
    if not text:
        return {}
    findings: dict[str, list[dict]] = {
        "aadhaar_devanagari": [],
        "aadhaar_bengali": [],
        "aadhaar_tamil": [],
        "aadhaar_latin": [],
        "indian_mobile": [],
        "pin_code": [],
        "pin_code_devanagari": [],
        "hindi_honorific": [],
    }

    # Latin-numeral Aadhaar (12 digits, first 2-9)
    aadhaar_latin = re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b")

    pattern_map = {
        "aadhaar_devanagari": AADHAAR_DEVANAGARI,
        "aadhaar_bengali": AADHAAR_BENGALI,
        "aadhaar_tamil": AADHAAR_TAMIL,
        "aadhaar_latin": aadhaar_latin,
        "indian_mobile": INDIAN_MOBILE,
        "pin_code": PIN_CODE,
        "pin_code_devanagari": PIN_CODE_DEVANAGARI,
        "hindi_honorific": HINDI_HONORIFIC_PARTICLES,
    }

    for kind, pattern in pattern_map.items():
        for m in pattern.finditer(text):
            findings[kind].append(
                {
                    "match": m.group(),
                    "start": m.start(),
                    "end": m.end(),
                    "line": text[: m.start()].count("\n") + 1,
                }
            )

    # Drop empty
    return {k: v for k, v in findings.items() if v}


def redact_indic_aadhaar(text: str) -> str:
    """Redact all Aadhaar numbers (Latin + Devanagari + Bengali + Tamil)
    to XXXX XXXX <last4>.
    """

    def _redact(m: re.Match) -> str:
        raw = m.group()
        digits = re.sub(r"\s", "", raw)
        # Convert Indic digits to ASCII for the last4
        ascii_digits = normalize_indic_digits(digits)
        if len(ascii_digits) >= 12 and ascii_digits.isascii():
            return f"XXXX XXXX {ascii_digits[-4:]}"
        return "XXXX XXXX XXXX"

    text = AADHAAR_DEVANAGARI.sub(_redact, text)
    text = AADHAAR_BENGALI.sub(_redact, text)
    text = AADHAAR_TAMIL.sub(_redact, text)
    aadhaar_latin = re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b")
    text = aadhaar_latin.sub(_redact, text)
    return text


# -------------------- Transliteration --------------------

# Minimal Devanagari → Latin (ITRANS-style) for the most common letters.
# This is NOT a comprehensive transliteration — for that, recommend the
# `indic-transliteration` library. This handles the 80% case for names.

DEVANAGARI_TO_LATIN = {
    # Vowels (independent)
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ii",
    "उ": "u",
    "ऊ": "uu",
    "ऋ": "Ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
    "अं": "am",
    "अः": "ah",
    # Consonants
    "क": "ka",
    "ख": "kha",
    "ग": "ga",
    "घ": "gha",
    "ङ": "nga",
    "च": "cha",
    "छ": "chha",
    "ज": "ja",
    "झ": "jha",
    "ञ": "nya",
    "ट": "Ta",
    "ठ": "Tha",
    "ड": "Da",
    "ढ": "Dha",
    "ण": "Na",
    "त": "ta",
    "थ": "tha",
    "द": "da",
    "ध": "dha",
    "न": "na",
    "प": "pa",
    "फ": "pha",
    "ब": "ba",
    "भ": "bha",
    "म": "ma",
    "य": "ya",
    "र": "ra",
    "ल": "la",
    "व": "va",
    "श": "sha",
    "ष": "Sha",
    "स": "sa",
    "ह": "ha",
    # Vowel signs (matras)
    "ा": "aa",
    "ि": "i",
    "ी": "ii",
    "ु": "u",
    "ू": "uu",
    "ृ": "Ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ं": "m",
    "ः": "h",
    "्": "",  # virama
    # Numerals
    **DEVANAGARI_DIGITS,
}


def transliterate_devanagari_to_latin(text: str) -> str:
    """Approximate Devanagari → Latin transliteration.

    Handles common Hindi name patterns. Not lossless — for a fully
    lossless conversion, use the `indic-transliteration` package.
    """
    out = []
    for ch in text:
        if ch in DEVANAGARI_TO_LATIN:
            out.append(DEVANAGARI_TO_LATIN[ch])
        else:
            out.append(ch)
    return "".join(out)


# -------------------- Indic-aware text utilities --------------------


def normalize_indic_whitespace(text: str) -> str:
    """Normalize whitespace + Unicode forms in Indic text."""
    if not text:
        return text
    # NFC normalization (canonical composition)
    text = unicodedata.normalize("NFC", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_likely_hindi(text: str, min_devanagari_ratio: float = 0.3) -> bool:
    """Heuristic: is this text likely Hindi/Marathi/Sanskrit?"""
    if not text:
        return False
    fractions = script_detect(text)
    return fractions.get("devanagari", 0.0) >= min_devanagari_ratio


def is_likely_indic(text: str, min_indic_ratio: float = 0.3) -> bool:
    """Heuristic: is this text in any Indic script?"""
    if not text:
        return False
    fractions = script_detect(text)
    indic_total = sum(fractions.get(s, 0.0) for s in SCRIPT_RANGES)
    return indic_total >= min_indic_ratio
