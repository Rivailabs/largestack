"""Toxicity and bias detection — multi-layer with ML model fallback."""
from __future__ import annotations
import re, logging
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.guard.toxicity")


# Patterns organized by category (not specific words, just instruction patterns)
VIOLENCE_INSTRUCTION_PATTERNS = [
    re.compile(r'\b(how|steps|tutorial|guide|instruct).{0,30}(kill|murder|attack|harm|hurt|injure)\b', re.I),
    re.compile(r'\b(make|build|create|construct).{0,30}(weapon|bomb|explosive|poison)\b', re.I),
    re.compile(r'\b(plan|plot|execute|carry out).{0,30}(assassination|shooting|terrorist)\b', re.I),
]

HATE_PATTERNS = [
    re.compile(r'\b(all|every).{0,15}(should be|deserve|must).{0,15}(killed|eliminated|destroyed)\b', re.I),
    re.compile(r'\b(exterminate|genocide|ethnic cleansing)\b', re.I),
    re.compile(r'\b(inferior|subhuman|vermin).{0,30}(race|people|group|religion)\b', re.I),
]

SELF_HARM_PATTERNS = [
    re.compile(r'\b(suicide|kill myself|end my life)\s+(method|how to|way to|instruction)', re.I),
    re.compile(r'\b(cut|harm|hurt) myself\b.{0,30}(effective|best|ways)', re.I),
]

SEXUAL_MINOR_PATTERNS = [
    re.compile(r'\b(child|minor|underage|teen|kid)\b.{0,20}(sexual|nude|explicit|naked)\b', re.I),
    re.compile(r'\b(sexual|nude|explicit|naked)\b.{0,20}(child|minor|underage|teen|kid)\b', re.I),
]

CATEGORY_PATTERNS = {
    "violence_instruction": VIOLENCE_INSTRUCTION_PATTERNS,
    "hate_speech": HATE_PATTERNS,
    "self_harm": SELF_HARM_PATTERNS,
    "sexual_minor": SEXUAL_MINOR_PATTERNS,
}


class ToxicityGuard:
    """Detect toxic, hateful, or harmful content.
    
    Layers:
      1. Pattern matching (fast, always-on) — instruction-pattern based
      2. ML classifier (optional) — detoxify or HuggingFace
      3. Custom classifier (plug-in callable)
    
        # Default: pattern matching
        guard = ToxicityGuard(sensitivity="medium")
        
        # With ML classifier
        guard = ToxicityGuard(use_ml=True)
        
        # Custom classifier function
        guard = ToxicityGuard(custom_classifier=my_fn)
    """
    def __init__(self, sensitivity: str = "medium", use_ml: bool = False,
                 custom_classifier=None, check_input_too: bool = False,
                 categories: list[str] = None):
        self.sensitivity = sensitivity
        self.check_input_too = check_input_too
        self.custom_classifier = custom_classifier
        self.categories = categories or list(CATEGORY_PATTERNS.keys())
        self._ml_classifier = None
        self._violation_count = 0
        
        if use_ml:
            try:
                from detoxify import Detoxify
                self._ml_classifier = Detoxify("original")
                log.info("ToxicityGuard: loaded detoxify ML model")
            except ImportError:
                log.warning("detoxify not installed — falling back to pattern matching. "
                            "pip install detoxify for ML toxicity detection.")
    
    def _thresholds(self) -> dict:
        """Sensitivity thresholds (min matches required)."""
        return {
            "low": 3,       # Multiple strong signals needed
            "medium": 1,    # Any clear pattern match
            "high": 1,      # Any match
        }
    
    async def check_input(self, messages):
        """Optionally check user input for toxic content."""
        if not self.check_input_too:
            return
        for m in messages:
            c = m.get("content", "")
            if isinstance(c, str):
                detection = self._detect(c)
                if detection["is_toxic"]:
                    self._violation_count += 1
                    raise GuardrailBlockedError(
                        "toxicity",
                        f"Toxic input detected: {detection['categories']} "
                        f"(score={detection['score']:.2f})"
                    )
    
    async def check_output(self, response) -> None:
        """Check LLM output for toxic content."""
        content = response.content if hasattr(response, "content") else str(response)
        if not isinstance(content, str):
            return
        
        detection = self._detect(content)
        if detection["is_toxic"]:
            self._violation_count += 1
            raise GuardrailBlockedError(
                "toxicity",
                f"Toxic output detected: {detection['categories']} "
                f"(score={detection['score']:.2f})"
            )
    
    def _detect(self, text: str) -> dict:
        """Detect toxicity across all layers. Returns detection details."""
        if not text or not text.strip():
            return {"is_toxic": False, "score": 0.0, "categories": [], "method": "empty"}
        
        # Layer 1: Pattern matching
        pattern_result = self._detect_patterns(text)
        if pattern_result["matched_categories"]:
            return {
                "is_toxic": True,
                "score": min(1.0, pattern_result["match_count"] / 2),
                "categories": pattern_result["matched_categories"],
                "method": "pattern",
            }
        
        # Layer 2: ML classifier
        if self._ml_classifier:
            try:
                scores = self._ml_classifier.predict(text)
                toxic_score = max(scores.values())
                if toxic_score > 0.7:  # ML threshold
                    cats = [k for k, v in scores.items() if v > 0.5]
                    return {
                        "is_toxic": True,
                        "score": toxic_score,
                        "categories": cats,
                        "method": "ml",
                    }
            except Exception as e:
                log.warning(f"ML classifier failed: {e}")
        
        # Layer 3: Custom classifier
        if self.custom_classifier:
            try:
                result = self.custom_classifier(text)
                if isinstance(result, dict) and result.get("is_toxic"):
                    return {**result, "method": "custom"}
                if result is True:
                    return {"is_toxic": True, "score": 1.0, "categories": ["custom"], "method": "custom"}
            except Exception as e:
                log.warning(f"Custom classifier failed: {e}")
        
        return {"is_toxic": False, "score": 0.0, "categories": [], "method": "clean"}
    
    def _detect_patterns(self, text: str) -> dict:
        """Check against instruction-pattern regexes."""
        matched = []
        count = 0
        for category in self.categories:
            patterns = CATEGORY_PATTERNS.get(category, [])
            for p in patterns:
                if p.search(text):
                    matched.append(category)
                    count += 1
        
        threshold = self._thresholds().get(self.sensitivity, 1)
        if count >= threshold:
            return {"matched_categories": list(set(matched)), "match_count": count}
        return {"matched_categories": [], "match_count": 0}
    
    def analyze(self, text: str) -> dict:
        """Public analyze method — returns detection details without raising."""
        return self._detect(text)
    
    @property
    def stats(self) -> dict:
        return {
            "sensitivity": self.sensitivity,
            "ml_enabled": self._ml_classifier is not None,
            "violation_count": self._violation_count,
            "categories_checked": self.categories,
        }
