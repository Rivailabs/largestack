"""Enhanced PII detection with optional ML models (Presidio + spaCy NER).

The ML passes run only when enabled (LARGESTACK_ENABLE_ML_PII=1) and the optional
deps are installed:
  Pass 1: Presidio regex rules (fast, ~0.2ms)
  Pass 2: spaCy NER for context-dependent entities (PERSON, ORG, GPE)
Otherwise this falls back to the built-in regex PII patterns (largestack._guard.pii).
"""
from __future__ import annotations
import logging
import os
from largestack._guard.pii import PIIGuard, PATTERNS
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.pii_ml")

class EnhancedPIIGuard(PIIGuard):
    """PII detection with ML model support."""
    
    def __init__(self, entities: list[str] = None, action: str = "redact", 
                 use_presidio: bool | None = None, use_spacy: bool | None = None):
        super().__init__(entities, action)
        self._presidio = None
        self._anonymizer = None
        self._spacy_nlp = None

        # Optional ML engines can add seconds to process startup and may pull in
        # heavyweight model initialization. Keep the default production-safe and
        # test-friendly: regex detection is always active, ML engines are enabled
        # only by explicit constructor flag or LARGESTACK_ENABLE_ML_PII=1.
        from largestack._guard.config import ml_guards_enabled
        ml_enabled = ml_guards_enabled("LARGESTACK_ENABLE_ML_PII")
        if use_presidio is None:
            use_presidio = ml_enabled
        if use_spacy is None:
            use_spacy = ml_enabled
        
        if use_presidio:
            try:
                from presidio_analyzer import AnalyzerEngine
                from presidio_anonymizer import AnonymizerEngine
                self._presidio = AnalyzerEngine()
                self._anonymizer = AnonymizerEngine()
                log.info("Presidio ML engine loaded")
            except ImportError:
                log.debug("Presidio not installed, using regex fallback")
        
        if use_spacy:
            try:
                import spacy
                try:
                    self._spacy_nlp = spacy.load("en_core_web_sm")
                except OSError:
                    try:
                        self._spacy_nlp = spacy.load("en_core_web_lg")
                    except OSError:
                        log.debug("spaCy model not found. Install: python -m spacy download en_core_web_sm")
            except ImportError:
                log.debug("spaCy not installed")
    
    def detect_entities(self, text: str) -> list[dict]:
        """Detect PII entities using all available methods."""
        entities = []
        
        # Pass 1: Presidio (if available)
        if getattr(self, "_presidio", None):
            results = self._presidio.analyze(text=text, language="en")
            for r in results:
                entities.append({
                    "type": r.entity_type, "start": r.start, "end": r.end,
                    "score": r.score, "text": text[r.start:r.end], "source": "presidio"
                })
        
        # Pass 2: spaCy NER (if available)
        if self._spacy_nlp:
            doc = self._spacy_nlp(text)
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG", "GPE", "FAC", "NORP"):
                    entities.append({
                        "type": ent.label_, "start": ent.start_char, "end": ent.end_char,
                        "score": 0.85, "text": ent.text, "source": "spacy"
                    })
        
        # Pass 3: Regex fallback (always runs)
        for entity_type, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                entities.append({
                    "type": entity_type.upper(), "start": match.start(), "end": match.end(),
                    "score": 0.95, "text": match.group(), "source": "regex"
                })
        
        return entities
    
    def redact_all(self, text: str) -> tuple[str, list[dict]]:
        """Redact PII and return redacted text + detected entities."""
        entities = self.detect_entities(text)
        if getattr(self, "_presidio", None) and getattr(self, "_anonymizer", None):
            from presidio_analyzer import AnalyzerEngine
            results = self._presidio.analyze(text=text, language="en")
            if results:
                text = self._anonymizer.anonymize(text=text, analyzer_results=results).text
                return text, entities
        # Fallback: regex redaction
        text = self.redact(text)
        return text, entities
