"""Hallucination detection — claim decomposition + context verification.

Method: Decompose response into atomic claims, verify each against source context.

Fast mode: keyword/entity overlap (no dependencies).
NLI mode: DeBERTa-v3-large-MNLI (AUC 0.81 from TruthfulQA benchmark).

Based on "SelfCheckGPT" (Manakul et al., 2023) and "FACTOID" methodology.
"""
from __future__ import annotations
import os
import re, logging
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.guard.hallucination")


# Patterns for extracting verifiable entities
NUMBER_RE = re.compile(r'\b\d{1,15}(?:[.,]\d+)?(?:%|°|°C|°F|[a-zA-Z]{0,5})?\b')
DATE_RE = re.compile(r'\b(?:\d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b')
PROPER_NOUN_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b')
EMAIL_RE = re.compile(r'\b[\w.-]+@[\w.-]+\.\w+\b')
URL_RE = re.compile(r'https?://\S+')


class HallucinationGuard:
    """Detect hallucinations via claim decomposition + verification.
    
    Layers:
      1. Fast: Keyword + entity overlap scoring
      2. Number verification: check cited numbers exist in context
      3. NLI model: DeBERTa-v3-large-MNLI for each claim
    
        guard = HallucinationGuard(threshold=0.5)
        guard.set_context(retrieved_context)
        # ... agent responds ...
        # Guard will block if response doesn't match context
        
        # With NLI
        guard = HallucinationGuard(mode="nli", threshold=0.7)
    """
    
    def __init__(self, threshold: float = 0.5, mode: str = "fast",
                 min_claim_length: int = 15, check_numbers: bool = True,
                 check_entities: bool = True, warn_only: bool = False):
        self.threshold = threshold
        self.mode = mode
        self.min_claim_length = min_claim_length
        self.check_numbers = check_numbers
        self.check_entities = check_entities
        self.warn_only = warn_only
        self._context: str = ""
        self._nli_model = None
        self._violation_count = 0
        
        if mode == "nli":
            nli_enabled = os.environ.get("LARGESTACK_ENABLE_NLI_GUARD", "").lower() in ("1", "true", "yes")
            if not nli_enabled:
                log.info("NLI mode requested but LARGESTACK_ENABLE_NLI_GUARD is not set; using fast mode.")
                self.mode = "fast"
            else:
                try:
                    from transformers import pipeline
                    self._nli_model = pipeline(
                        "text-classification",
                        model="MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
                    )
                    log.info("HallucinationGuard: loaded DeBERTa NLI model")
                except Exception as exc:
                    log.warning("NLI mode unavailable (%s). Install/repair transformers + torch "
                                "to enable model-backed hallucination checks; falling back to fast mode.", exc)
                    self.mode = "fast"
    
    def set_context(self, context: str):
        """Set RAG context to verify against."""
        self._context = context
    
    def clear_context(self):
        self._context = ""
    
    async def check_input(self, messages):
        """No input check — only verifies output against context."""
        pass
    
    async def check_output(self, response) -> None:
        if not self._context:
            return  # No context → can't verify
        
        content = response.content if hasattr(response, "content") else str(response)
        if not isinstance(content, str) or not content.strip():
            return
        
        analysis = self._analyze(content, self._context)
        
        if analysis["faithfulness"] < self.threshold:
            self._violation_count += 1
            msg = (f"Faithfulness {analysis['faithfulness']:.2f} < {self.threshold} "
                   f"({analysis['unverified_claims']} unverified claims)")
            if self.warn_only:
                log.warning(f"HallucinationGuard: {msg}")
            else:
                raise GuardrailBlockedError("hallucination", msg)
    
    def _analyze(self, response: str, context: str) -> dict:
        """Analyze response faithfulness against context."""
        claims = self._decompose_claims(response)
        if not claims:
            return {"faithfulness": 1.0, "claim_count": 0, "unverified_claims": 0, "claims": []}
        
        verified = 0
        unverified = []
        claim_scores = []
        
        for claim in claims:
            if self.mode == "nli" and self._nli_model:
                score = self._nli_score(claim, context)
            else:
                score = self._fast_score(claim, context)
            
            claim_scores.append({"claim": claim, "score": score, "verified": score >= 0.5})
            if score >= 0.5:
                verified += 1
            else:
                unverified.append(claim)
        
        return {
            "faithfulness": verified / len(claims),
            "claim_count": len(claims),
            "verified_claims": verified,
            "unverified_claims": len(unverified),
            "unverified_samples": unverified[:3],
            "claims": claim_scores,
            "mode": self.mode,
        }
    
    def _decompose_claims(self, text: str) -> list[str]:
        """Split text into verifiable claim sentences.
        
        Filters out: questions, imperatives, very short fragments.
        """
        sentences = re.split(r'(?<=[.!?])\s+', text)
        claims = []
        for s in sentences:
            s = s.strip()
            if len(s) < self.min_claim_length:
                continue
            # Skip questions
            if s.endswith("?"):
                continue
            # Skip pure imperatives (single word + punctuation is not a claim)
            words = s.split()
            if len(words) < 4:
                continue
            claims.append(s)
        return claims
    
    def _fast_score(self, claim: str, context: str) -> float:
        """Fast keyword + entity overlap scoring."""
        claim_lower = claim.lower()
        context_lower = context.lower()
        
        scores = []
        
        # 1. Keyword overlap (filter stopwords)
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                     "being", "have", "has", "had", "do", "does", "did", "will",
                     "would", "could", "should", "may", "might", "must", "can",
                     "this", "that", "these", "those", "of", "in", "on", "at",
                     "to", "for", "with", "by", "from", "as", "but", "and", "or",
                     "if", "then", "else"}
        claim_words = set(claim_lower.split()) - stopwords
        context_words = set(context_lower.split()) - stopwords
        if claim_words:
            scores.append(len(claim_words & context_words) / len(claim_words))
        
        # 2. Number verification (if present in claim)
        if self.check_numbers:
            claim_numbers = set(NUMBER_RE.findall(claim))
            if claim_numbers:
                # Remove formatting differences
                normalized_claim = {n.replace(",", "") for n in claim_numbers}
                normalized_context = {n.replace(",", "") for n in NUMBER_RE.findall(context)}
                # Every number in claim must appear in context
                scores.append(
                    len(normalized_claim & normalized_context) / len(normalized_claim)
                )
        
        # 3. Entity verification (proper nouns)
        if self.check_entities:
            claim_entities = set(PROPER_NOUN_RE.findall(claim))
            if claim_entities:
                context_entities = set(PROPER_NOUN_RE.findall(context))
                scores.append(
                    len(claim_entities & context_entities) / len(claim_entities)
                )
        
        # 4. Date verification
        claim_dates = set(DATE_RE.findall(claim))
        if claim_dates:
            context_dates = set(DATE_RE.findall(context))
            scores.append(
                len(claim_dates & context_dates) / len(claim_dates)
            )
        
        return sum(scores) / len(scores) if scores else 0.5
    
    def _nli_score(self, claim: str, context: str) -> float:
        """NLI-based score: is claim entailed by context?"""
        try:
            # NLI input: "premise </s> hypothesis"
            result = self._nli_model(f"{context[:2000]} </s> {claim}")
            if isinstance(result, list) and result:
                label = result[0]["label"].lower()
                score = result[0]["score"]
                if "entail" in label:
                    return score
                elif "contradict" in label:
                    return 0.0
                else:  # neutral
                    return 0.3
            return 0.5
        except Exception as e:
            log.warning(f"NLI scoring failed: {e}, falling back to fast")
            return self._fast_score(claim, context)
    
    def analyze(self, response: str, context: str = None) -> dict:
        """Public analyze method."""
        ctx = context if context is not None else self._context
        return self._analyze(response, ctx)
    
    @property
    def stats(self) -> dict:
        return {
            "mode": self.mode,
            "threshold": self.threshold,
            "nli_enabled": self._nli_model is not None,
            "violation_count": self._violation_count,
        }
