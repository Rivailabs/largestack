"""v0.11.0: Tests for Indic NLP module — the moat extension."""

from __future__ import annotations

import pytest


# -------------------- Script detection --------------------


def test_script_detect_devanagari_dominant():
    from largestack._indic import script_detect

    text = "मेरा नाम सचिथ है। My name is Sachith."
    fractions = script_detect(text)
    # Should have both devanagari and latin, devanagari should be present
    assert fractions.get("devanagari", 0) > 0
    assert fractions.get("latin", 0) > 0


def test_primary_script():
    from largestack._indic import primary_script

    assert primary_script("Hello world") == "latin"
    assert primary_script("नमस्ते दुनिया") == "devanagari"
    assert primary_script("வணக்கம் உலகம்") == "tamil"
    assert primary_script("నమస్కారం ప్రపంచం") == "telugu"
    assert primary_script("নমস্কার বিশ্ব") == "bengali"
    assert primary_script("") == "unknown"


def test_script_detect_pure_hindi():
    from largestack._indic import script_detect

    fractions = script_detect("भारत एक महान देश है।")
    assert fractions.get("devanagari", 0) > 0.8


# -------------------- Tokenizer --------------------


def test_indic_tokenizer_sentences_with_danda():
    from largestack._indic import IndicTokenizer

    tk = IndicTokenizer()
    text = "मैं भारत से हूं। मेरा नाम राहुल है। आप कैसे हैं?"
    sentences = tk.sentences(text)
    assert len(sentences) >= 3


def test_indic_tokenizer_mixed_script():
    """Indic + Latin mixed text — common in Indian content."""
    from largestack._indic import IndicTokenizer

    tk = IndicTokenizer()
    text = "Hello world. नमस्ते भाई। How are you? मैं ठीक हूं।"
    sentences = tk.sentences(text)
    assert len(sentences) >= 4


def test_indic_tokenizer_words():
    from largestack._indic import IndicTokenizer

    tk = IndicTokenizer()
    words = tk.words("मेरा नाम राहुल कुमार है")
    assert "मेरा" in words
    assert "राहुल" in words
    assert "कुमार" in words


def test_indic_tokenizer_handles_empty():
    from largestack._indic import IndicTokenizer

    tk = IndicTokenizer()
    assert tk.sentences("") == []
    assert tk.words("") == []
    assert tk.sentences("   ") == []


# -------------------- Indic numeral normalization --------------------


def test_normalize_devanagari_digits():
    from largestack._indic import normalize_indic_digits

    # Devanagari "12345" → ASCII "12345"
    assert normalize_indic_digits("१२३४५") == "12345"
    assert normalize_indic_digits("१२३४ ५६७८ ९०१२") == "1234 5678 9012"


def test_normalize_bengali_digits():
    from largestack._indic import normalize_indic_digits

    assert normalize_indic_digits("১২৩৪৫") == "12345"


def test_normalize_tamil_digits():
    from largestack._indic import normalize_indic_digits

    assert normalize_indic_digits("௧௨௩௪௫") == "12345"


def test_normalize_telugu_digits():
    from largestack._indic import normalize_indic_digits

    assert normalize_indic_digits("౧౨౩౪౫") == "12345"


def test_normalize_keeps_non_digit_chars():
    from largestack._indic import normalize_indic_digits

    text = "मेरा फोन: ९८७६५४३२१०"
    result = normalize_indic_digits(text)
    assert "9876543210" in result
    assert "मेरा" in result  # Hindi word preserved


# -------------------- PII detection (Indic) --------------------


def test_detect_aadhaar_in_devanagari():
    from largestack._indic import detect_indic_pii

    # Aadhaar starting with 2-9, in Devanagari
    text = "मेरा आधार नंबर है: २३४५ ६७८९ ०१२३"
    findings = detect_indic_pii(text)
    assert "aadhaar_devanagari" in findings
    assert len(findings["aadhaar_devanagari"]) == 1


def test_detect_aadhaar_in_bengali():
    from largestack._indic import detect_indic_pii

    text = "আমার আধার: ২৩৪৫ ৬৭৮৯ ০১২৩"
    findings = detect_indic_pii(text)
    assert "aadhaar_bengali" in findings


def test_detect_aadhaar_in_tamil():
    from largestack._indic import detect_indic_pii

    text = "என் ஆதார்: ௨௩௪௫ ௬௭௮௯ ௦௧௨௩"
    findings = detect_indic_pii(text)
    assert "aadhaar_tamil" in findings


def test_detect_indian_mobile_formats():
    from largestack._indic import detect_indic_pii

    formats = [
        "+91-9876543210",
        "+91 9876543210",
        "09876543210",
        "9876543210",
    ]
    for fmt in formats:
        findings = detect_indic_pii(f"Contact me at {fmt}")
        assert "indian_mobile" in findings, f"Failed for: {fmt}"


def test_detect_pin_code():
    from largestack._indic import detect_indic_pii

    text = "Bengaluru 560074"
    findings = detect_indic_pii(text)
    assert "pin_code" in findings


def test_detect_pin_code_devanagari():
    from largestack._indic import detect_indic_pii

    text = "बेंगलुरु ५६००७४"
    findings = detect_indic_pii(text)
    assert "pin_code_devanagari" in findings


def test_detect_hindi_honorific():
    from largestack._indic import detect_indic_pii

    text = "श्री रमेश कुमार और श्रीमती सीता देवी"
    findings = detect_indic_pii(text)
    assert "hindi_honorific" in findings
    assert len(findings["hindi_honorific"]) >= 2  # both श्री and श्रीमती


def test_detect_no_pii_in_clean_text():
    from largestack._indic import detect_indic_pii

    findings = detect_indic_pii("नमस्ते दुनिया, यह सुरक्षित है")
    assert findings == {}


# -------------------- Indic Aadhaar redaction --------------------


def test_redact_devanagari_aadhaar():
    from largestack._indic import redact_indic_aadhaar

    text = "आधार: २३४५ ६७८९ ०१२३ है"
    redacted = redact_indic_aadhaar(text)
    # Original Aadhaar should be gone
    assert "२३४५" not in redacted
    # Mask should be present with last 4
    assert "XXXX XXXX 0123" in redacted


def test_redact_latin_aadhaar():
    from largestack._indic import redact_indic_aadhaar

    text = "Aadhaar: 2345 6789 0123 verified"
    redacted = redact_indic_aadhaar(text)
    assert "2345 6789 0123" not in redacted
    assert "XXXX XXXX 0123" in redacted


def test_redact_bengali_aadhaar():
    from largestack._indic import redact_indic_aadhaar

    text = "আধার: ২৩৪৫ ৬৭৮৯ ০১২৩"
    redacted = redact_indic_aadhaar(text)
    assert "২৩৪৫" not in redacted
    assert "XXXX XXXX 0123" in redacted


def test_redact_preserves_other_text():
    from largestack._indic import redact_indic_aadhaar

    text = "नाम: राहुल, आधार: २३४५ ६७८९ ०१२३, फोन: ९८७६५४३२१०"
    redacted = redact_indic_aadhaar(text)
    # Hindi name preserved
    assert "राहुल" in redacted
    # Aadhaar redacted
    assert "XXXX XXXX 0123" in redacted


# -------------------- Transliteration --------------------


def test_transliterate_basic_hindi():
    from largestack._indic import transliterate_devanagari_to_latin

    # नमस्ते (namaste) — should produce something Latin-readable
    result = transliterate_devanagari_to_latin("नमस्ते")
    assert all(ord(c) < 128 for c in result), f"non-ASCII output: {result}"


def test_transliterate_devanagari_digits():
    from largestack._indic import transliterate_devanagari_to_latin

    assert "1234" in transliterate_devanagari_to_latin("१२३४")


def test_transliterate_preserves_latin():
    from largestack._indic import transliterate_devanagari_to_latin

    result = transliterate_devanagari_to_latin("Hello नमस्ते")
    assert "Hello" in result


# -------------------- is_likely helpers --------------------


def test_is_likely_hindi():
    from largestack._indic import is_likely_hindi

    assert is_likely_hindi("नमस्ते दुनिया") is True
    assert is_likely_hindi("Hello world") is False
    # Mixed text — depends on threshold
    assert is_likely_hindi("Hello नमस्ते दुनिया मेरा नाम") is True


def test_is_likely_indic():
    from largestack._indic import is_likely_indic

    assert is_likely_indic("நமஸ்கார") is True  # Tamil
    assert is_likely_indic("নমস্কার") is True  # Bengali
    assert is_likely_indic("నమస్కారం") is True  # Telugu
    assert is_likely_indic("Hello world") is False


# -------------------- Whitespace normalization --------------------


def test_normalize_indic_whitespace():
    from largestack._indic import normalize_indic_whitespace

    text = "मेरा   नाम\n\nराहुल   है"
    result = normalize_indic_whitespace(text)
    assert "मेरा नाम राहुल है" == result
