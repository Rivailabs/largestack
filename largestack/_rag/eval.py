"""RAG evaluation framework (v0.9.0).

Implements the four canonical RAG metrics:
- ``faithfulness`` — does the answer derive from the retrieved context?
- ``answer_relevance`` — does the answer address the question?
- ``context_precision`` — are relevant chunks ranked first?
- ``context_recall`` — is all required info in the retrieved context?

Each metric is implemented as an LLM-judge prompt. Pass any agent /
LLM-callable; the metric returns a score in [0, 1].
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.rag_eval")


# -------------------- Metric prompts --------------------

FAITHFULNESS_PROMPT = """You are evaluating whether the following answer \
is FAITHFUL to the provided context. An answer is faithful if every claim \
in it can be verified from the context.

Context:
{context}

Question: {question}

Answer: {answer}

Score the faithfulness from 0 to 10 (10 = perfectly faithful, 0 = entirely \
fabricated). Output ONLY a JSON object: {{"score": <0-10>, "reasoning": "<brief>"}}"""


ANSWER_RELEVANCE_PROMPT = """You are evaluating whether the following answer \
is RELEVANT to the question. An answer is relevant if it directly addresses \
what was asked, regardless of correctness.

Question: {question}

Answer: {answer}

Score the relevance from 0 to 10 (10 = perfectly addresses question, \
0 = completely off-topic). Output ONLY a JSON object: \
{{"score": <0-10>, "reasoning": "<brief>"}}"""


CONTEXT_PRECISION_PROMPT = """You are evaluating CONTEXT PRECISION: \
how well were the most relevant chunks ranked at the top?

Question: {question}

Retrieved chunks (in order):
{chunks}

For each chunk, decide if it's relevant to answering the question. \
Score precision = (# relevant chunks in top half) / (# chunks in top half). \
Output ONLY: {{"score": <0-10>, "reasoning": "<brief>"}}"""


CONTEXT_RECALL_PROMPT = """You are evaluating CONTEXT RECALL: \
does the retrieved context contain ALL info needed to answer correctly?

Ground truth answer: {ground_truth}

Retrieved context:
{context}

Score recall from 0 to 10 (10 = all required info is present, \
0 = nothing relevant retrieved). Output ONLY: \
{{"score": <0-10>, "reasoning": "<brief>"}}"""


# -------------------- Result types --------------------

@dataclass
class MetricResult:
    """Single metric result."""
    metric: str
    score: float        # in [0, 1] (normalized from raw 0-10)
    raw_score: float    # the raw 0-10 score
    reasoning: str = ""


@dataclass
class EvalResult:
    """Full evaluation across all metrics."""
    question: str
    answer: str
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    @property
    def average_score(self) -> float:
        """Average of all metric scores (in [0, 1])."""
        if not self.metrics:
            return 0.0
        return sum(m.score for m in self.metrics.values()) / len(self.metrics)


# -------------------- Helpers --------------------

def _parse_score(text: str) -> tuple[float, str]:
    """Extract score + reasoning from LLM judge output."""
    # Try to find JSON anywhere in text
    text = text.strip()
    for fence in ["```json", "```"]:
        text = text.replace(fence, "")
    text = text.strip()
    try:
        data = json.loads(text)
        score = float(data.get("score", 0))
        reasoning = str(data.get("reasoning", ""))
        return score, reasoning
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: regex
        m = re.search(r'"score"\s*:\s*([\d.]+)', text)
        if m:
            try:
                return float(m.group(1)), text[:200]
            except ValueError:
                pass
        # Last resort: any number
        m = re.search(r"\b([0-9](?:\.\d+)?|10)\b", text)
        if m:
            try:
                return float(m.group(1)), text[:200]
            except ValueError:
                pass
    return 0.0, text[:200]


async def _run_judge(judge_agent, prompt: str) -> tuple[float, str]:
    """Call the judge and parse score (0-10)."""
    try:
        result = await judge_agent.run(prompt)
        content = getattr(result, "content", "") or ""
    except Exception as e:
        return 0.0, f"judge error: {e}"
    return _parse_score(content)


# -------------------- Metric functions --------------------

async def faithfulness(
    judge_agent, *, question: str, answer: str, context: str,
) -> MetricResult:
    """Faithfulness: does the answer come from the context?"""
    prompt = FAITHFULNESS_PROMPT.format(
        question=question, answer=answer, context=context,
    )
    raw, reasoning = await _run_judge(judge_agent, prompt)
    raw = max(0.0, min(10.0, raw))
    return MetricResult(
        metric="faithfulness",
        score=raw / 10.0, raw_score=raw, reasoning=reasoning,
    )


async def answer_relevance(
    judge_agent, *, question: str, answer: str,
) -> MetricResult:
    """Answer relevance: does the answer address the question?"""
    prompt = ANSWER_RELEVANCE_PROMPT.format(question=question, answer=answer)
    raw, reasoning = await _run_judge(judge_agent, prompt)
    raw = max(0.0, min(10.0, raw))
    return MetricResult(
        metric="answer_relevance",
        score=raw / 10.0, raw_score=raw, reasoning=reasoning,
    )


async def context_precision(
    judge_agent, *, question: str, retrieved_chunks: list[str],
) -> MetricResult:
    """Context precision: are relevant chunks ranked at the top?"""
    chunks_text = "\n\n".join(
        f"[{i + 1}] {c[:500]}"
        for i, c in enumerate(retrieved_chunks)
    )
    prompt = CONTEXT_PRECISION_PROMPT.format(
        question=question, chunks=chunks_text,
    )
    raw, reasoning = await _run_judge(judge_agent, prompt)
    raw = max(0.0, min(10.0, raw))
    return MetricResult(
        metric="context_precision",
        score=raw / 10.0, raw_score=raw, reasoning=reasoning,
    )


async def context_recall(
    judge_agent, *, ground_truth: str, context: str,
) -> MetricResult:
    """Context recall: does context contain all needed info?"""
    prompt = CONTEXT_RECALL_PROMPT.format(
        ground_truth=ground_truth, context=context,
    )
    raw, reasoning = await _run_judge(judge_agent, prompt)
    raw = max(0.0, min(10.0, raw))
    return MetricResult(
        metric="context_recall",
        score=raw / 10.0, raw_score=raw, reasoning=reasoning,
    )


# -------------------- Convenience: evaluate all --------------------

async def evaluate(
    judge_agent,
    *,
    question: str,
    answer: str,
    context: str,
    retrieved_chunks: list[str] | None = None,
    ground_truth: str | None = None,
) -> EvalResult:
    """Run all applicable RAG metrics.

    Args:
        judge_agent: agent used for LLM-judge scoring.
        question: original question.
        answer: agent's answer.
        context: concatenated retrieved context (for faithfulness/recall).
        retrieved_chunks: per-chunk list (for precision).
        ground_truth: known correct answer (for recall).
    """
    result = EvalResult(question=question, answer=answer)

    # Always-runnable
    result.metrics["faithfulness"] = await faithfulness(
        judge_agent, question=question, answer=answer, context=context,
    )
    result.metrics["answer_relevance"] = await answer_relevance(
        judge_agent, question=question, answer=answer,
    )

    # Conditionally runnable
    if retrieved_chunks:
        result.metrics["context_precision"] = await context_precision(
            judge_agent, question=question, retrieved_chunks=retrieved_chunks,
        )
    if ground_truth:
        result.metrics["context_recall"] = await context_recall(
            judge_agent, ground_truth=ground_truth, context=context,
        )

    return result
