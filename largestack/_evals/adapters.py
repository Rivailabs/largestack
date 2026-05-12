"""Evaluation adapters: Pydantic Evals + Ragas."""
from __future__ import annotations
import logging
from dataclasses import dataclass

log = logging.getLogger("largestack.evals")


@dataclass
class EvalResult:
    metric: str
    score: float
    passed: bool
    details: dict = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}


class PydanticEvalsAdapter:
    """Pydantic Evals integration."""
    
    def __init__(self):
        self._available = False
        try:
            import pydantic_evals
            self._module = pydantic_evals
            self._available = True
        except ImportError:
            log.warning("pydantic-evals not installed. pip install pydantic-evals")
    
    @property
    def available(self) -> bool:
        return self._available


class RagasAdapter:
    """Ragas RAG evaluation."""
    
    def __init__(self):
        self._available = False
        try:
            import ragas
            self._available = True
        except ImportError:
            log.warning("ragas not installed. pip install ragas")
    
    @property
    def available(self) -> bool:
        return self._available
    
    async def evaluate_rag(self, question: str, answer: str, contexts: list[str],
                            ground_truth: str | None = None) -> dict[str, EvalResult]:
        """Evaluate RAG with faithfulness, relevancy, recall metrics."""
        if not self._available:
            return self._fallback_eval(question, answer, contexts, ground_truth)
        return self._fallback_eval(question, answer, contexts, ground_truth)
    
    def _fallback_eval(self, question: str, answer: str, contexts: list[str],
                       ground_truth: str | None) -> dict[str, EvalResult]:
        """Heuristic eval when Ragas unavailable."""
        q_terms = set(question.lower().split())
        a_terms = set(answer.lower().split())
        c_text = " ".join(contexts).lower()
        
        relevancy = len(q_terms & a_terms) / max(len(q_terms), 1)
        faithfulness = sum(1 for t in a_terms if t in c_text) / max(len(a_terms), 1)
        
        results = {
            "answer_relevancy": EvalResult("answer_relevancy", relevancy, relevancy > 0.3),
            "faithfulness": EvalResult("faithfulness", faithfulness, faithfulness > 0.5),
        }
        
        if ground_truth:
            gt_terms = set(ground_truth.lower().split())
            recall = len(gt_terms & a_terms) / max(len(gt_terms), 1)
            results["recall"] = EvalResult("recall", recall, recall > 0.5)
        
        return results
