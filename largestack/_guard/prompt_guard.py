"""PromptGuard 2 — optional ML injection detector (Meta's 86M-param model).

Model: meta-llama/Prompt-Guard-2 (DeBERTa-based). Meta reports ~97.5% recall at 1%
FPR for THAT model on its benchmark. The ML model is loaded only when enabled via
LARGESTACK_ENABLE_PROMPT_GUARD_ML=1 (and transformers is installed); OTHERWISE the
default is the regex/pattern fallback (largestack._guard.injection), which does NOT
achieve those numbers.
"""

from __future__ import annotations
import logging
import os
from largestack._guard.injection import InjectionGuard, PATTERNS
from largestack.errors import GuardrailBlockedError

log = logging.getLogger("largestack.prompt_guard")


class PromptGuard2(InjectionGuard):
    """ML-based prompt injection detection using PromptGuard 2."""

    def __init__(
        self,
        threshold: float = 0.85,
        sensitivity: str = "medium",
        model_name: str = "meta-llama/Prompt-Guard-2-86M",
        revision: str | None = None,
    ):
        super().__init__(sensitivity)
        self.threshold = threshold
        self._model = None
        self._tokenizer = None
        self.model_name = model_name
        self.model_revision = revision or os.environ.get(
            "LARGESTACK_PROMPT_GUARD_MODEL_REVISION", "main"
        )

        from largestack._guard.config import ml_guards_enabled

        ml_enabled = ml_guards_enabled("LARGESTACK_ENABLE_PROMPT_GUARD_ML")
        if not ml_enabled:
            log.info(
                "PromptGuard ML model loading skipped; set LARGESTACK_ENABLE_PROMPT_GUARD_ML=1 to enable it"
            )
            return

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            import torch  # noqa: F401

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                revision=self.model_revision,
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                revision=self.model_revision,
            )
            self._model.eval()
            log.info("PromptGuard 2 model loaded: %s@%s", self.model_name, self.model_revision)
        except Exception as e:
            log.debug(f"PromptGuard 2 not available ({e}), using pattern fallback")

    def _ml_detect(self, text: str) -> float:
        """Run PromptGuard 2 model. Returns injection probability 0-1."""
        try:
            import torch

            inputs = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                outputs = self._model(**inputs)
                probs = torch.softmax(outputs.logits, dim=-1)
                # Class 1 = injection, Class 2 = jailbreak
                injection_score = probs[0][1].item() + probs[0][2].item()
                return injection_score
        except Exception:
            return 0.0
