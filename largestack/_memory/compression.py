"""Context compression — reduce token count while preserving meaning.

LLMLingua: 20x compression with 1.5% quality loss.
Fallback: extractive summarization when LLMLingua not installed.
"""

from __future__ import annotations
import re


class ContextCompressor:
    """Compress context to fit within token budgets.

    Methods:
        extractive: Remove low-information sentences (default)
        llmlingua: GPT-2 perplexity-based token pruning (if installed)
    """

    def __init__(self, method: str = "extractive", target_ratio: float = 0.3):
        self.method = method
        self.target_ratio = target_ratio

    def compress(self, text: str, max_tokens: int = None) -> str:
        """Compress text to target ratio or max_tokens."""
        if self.method == "llmlingua":
            return self._llmlingua_compress(text, max_tokens)
        return self._extractive_compress(text, max_tokens)

    def _extractive_compress(self, text: str, max_tokens: int = None) -> str:
        """Remove low-information sentences based on word importance."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) <= 3:
            return text

        # Score sentences by information density
        all_words = text.lower().split()
        word_freq = {}
        for w in all_words:
            word_freq[w] = word_freq.get(w, 0) + 1

        scored = []
        for sent in sentences:
            words = sent.lower().split()
            if not words:
                continue
            # Prefer sentences with rare words (higher information)
            avg_rarity = sum(1.0 / word_freq.get(w, 1) for w in words) / len(words)
            # Boost for sentences with numbers, proper nouns
            has_numbers = bool(re.search(r"\d+", sent))
            has_caps = bool(re.search(r"[A-Z][a-z]+", sent[1:]))
            score = avg_rarity + (0.3 if has_numbers else 0) + (0.2 if has_caps else 0)
            scored.append((score, sent))

        scored.sort(reverse=True)

        # Keep top sentences up to target
        target = max_tokens or int(len(text.split()) * self.target_ratio)
        kept = []
        token_count = 0
        for score, sent in scored:
            tokens = len(sent.split())
            if token_count + tokens > target and kept:
                break
            kept.append(sent)
            token_count += tokens

        # Re-order by original position
        original_order = {sent: i for i, sent in enumerate(sentences)}
        kept.sort(key=lambda s: original_order.get(s, 999))

        if not kept:
            kept = [scored[0][1]] if scored else []
        return " ".join(kept)[: target * 5]  # Hard character limit fallback

    def _llmlingua_compress(self, text: str, max_tokens: int = None) -> str:
        """Use LLMLingua for compression (requires llmlingua package)."""
        try:
            from llmlingua import PromptCompressor

            compressor = PromptCompressor()
            result = compressor.compress_prompt(text, rate=self.target_ratio)
            return result.get("compressed_prompt", text)
        except ImportError:
            return self._extractive_compress(text, max_tokens)
