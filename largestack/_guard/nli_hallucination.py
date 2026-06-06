"""NLI-based hallucination detection using DeBERTa-v3-large-MNLI (opt-in).

The AUC≈0.81 figure refers to the published DeBERTa-v3-large-MNLI model. The model
loads only when transformers is installed (else keyword fallback). Decomposes a
response into claims and checks each against context via NLI entailment.
"""
from __future__ import annotations
import logging
import os
from largestack._guard.hallucination import HallucinationGuard
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.nli")

class NLIHallucinationGuard(HallucinationGuard):
    """DeBERTa NLI-based hallucination detection."""
    
    def __init__(
        self,
        threshold: float = 0.5,
        model_name: str = "microsoft/deberta-v3-large-mnli",
        revision: str | None = None,
    ):
        super().__init__(threshold, mode="nli")
        self._nli_model = None
        self._nli_tokenizer = None
        self.model_name = model_name
        self.model_revision = revision or os.environ.get("LARGESTACK_NLI_MODEL_REVISION", "main")

        from largestack._guard.config import ml_guards_enabled
        nli_enabled = ml_guards_enabled("LARGESTACK_ENABLE_NLI_GUARD")
        if not nli_enabled:
            log.info("NLI model loading skipped; set LARGESTACK_ENABLE_NLI_GUARD=1 to enable it")
            return

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch  # noqa: F401

            self._nli_tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                revision=self.model_revision,
            )
            self._nli_model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                revision=self.model_revision,
            )
            self._nli_model.eval()
            log.info("NLI model loaded: %s@%s", self.model_name, self.model_revision)
        except Exception as e:
            log.debug(f"NLI model not available ({e}), using keyword fallback")

    def _nli_score(self, claim: str, context: str) -> float:
        """Override the base guard's enforcement-path NLI scorer.

        v1.1.1: the base ``_nli_score`` calls ``self._nli_model("premise </s> hyp")``
        with a raw STRING, but here ``_nli_model`` is an ``AutoModelForSequenceClassification``
        that needs tokenized tensors — so it always raised and silently fell back to
        keyword mode even when DeBERTa was loaded. Route through the tokenizing
        ``check_nli`` so the loaded model is actually used.
        """
        result = self.check_nli(premise=context[:2000], hypothesis=claim)
        if result.get("contradiction", 0.0) > result.get("entailment", 0.0):
            return 0.0
        return float(result.get("entailment", 0.5))

    def check_nli(self, premise: str, hypothesis: str) -> dict:
        """Check if hypothesis is entailed by premise.

        Returns: {entailment, neutral, contradiction} probabilities
        """
        if not self._nli_model:
            return self._keyword_nli(premise, hypothesis)
        
        try:
            import torch
            inputs = self._nli_tokenizer(premise, hypothesis, return_tensors="pt",
                                          truncation=True, max_length=512)
            with torch.no_grad():
                outputs = self._nli_model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)[0]
                # DeBERTa MNLI: [contradiction, neutral, entailment]
                return {
                    "contradiction": probs[0].item(),
                    "neutral": probs[1].item(),
                    "entailment": probs[2].item(),
                }
        except Exception:
            return self._keyword_nli(premise, hypothesis)
    
    def _keyword_nli(self, premise: str, hypothesis: str) -> dict:
        """Fallback: keyword overlap as proxy for entailment."""
        p_words = set(premise.lower().split())
        h_words = set(hypothesis.lower().split())
        overlap = len(p_words & h_words) / max(len(h_words), 1)
        return {
            "entailment": overlap,
            "neutral": (1 - overlap) * 0.5,
            "contradiction": (1 - overlap) * 0.5,
        }
    
    def check_faithfulness_nli(self, response: str, context: str) -> float:
        """Score faithfulness using NLI on decomposed claims."""
        claims = self._decompose_claims(response)
        if not claims:
            return 1.0
        
        entailed = 0
        for claim in claims:
            result = self.check_nli(premise=context, hypothesis=claim)
            if result["entailment"] > 0.5:
                entailed += 1
        
        return entailed / len(claims)
