"""CRAG — Corrective RAG with confidence evaluation.

Evaluates retrieval confidence:
  - Confident (>0.7): use retrieved docs
  - Ambiguous (0.3-0.7): combine retrieved + web search
  - Not confident (<0.3): fall back to web search
"""
from __future__ import annotations

class CRAGEvaluator:
    """Evaluate retrieval confidence and decide action."""
    
    def __init__(self, confident_threshold: float = 0.7, ambiguous_threshold: float = 0.3):
        self.confident = confident_threshold
        self.ambiguous = ambiguous_threshold
    
    def evaluate(self, query: str, results: list[dict]) -> dict:
        """Evaluate retrieval quality and recommend action."""
        if not results:
            return {"action": "web_search", "confidence": 0.0, "reason": "No results found"}
        
        # Calculate confidence from result scores
        scores = [r.get("score", 0) or r.get("rerank_score", 0) for r in results]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0
        
        # Normalize to 0-1 range
        confidence = min(max_score, 1.0) if max_score <= 1.0 else min(max_score / 10, 1.0)
        
        if confidence >= self.confident:
            return {"action": "proceed", "confidence": confidence, "reason": "High confidence retrieval"}
        elif confidence >= self.ambiguous:
            return {"action": "combine", "confidence": confidence, "reason": "Ambiguous — combine with web"}
        else:
            return {"action": "web_search", "confidence": confidence, "reason": "Low confidence — web fallback"}
    
    def filter_relevant(self, results: list[dict], min_score: float = 0.1) -> list[dict]:
        """Remove irrelevant results below minimum score."""
        return [r for r in results if (r.get("score", 0) or r.get("rerank_score", 0)) >= min_score]
