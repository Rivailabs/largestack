"""SubQuestion + Router query engines (v0.9.0).

Two final advanced RAG patterns:

1. **SubQuestionQueryEngine** — break a complex query into sub-questions,
   answer each separately (potentially against different retrievers),
   then synthesize a final answer. Best for cross-document or multi-hop
   questions ("Compare X and Y on dimension Z").

2. **RouterQueryEngine** — route a query to the appropriate sub-engine
   from a registry. The classifier LLM picks "use vector search" vs
   "use SQL agent" vs "use web search" based on query intent.
"""
from __future__ import annotations
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

log = logging.getLogger("largestack.rag.query_engines")


# -------------------- SubQuestion Query Engine --------------------

DECOMPOSITION_PROMPT = """Break this question into 2-5 simpler sub-questions \
that can be answered independently. Output ONLY a JSON array of strings.

Question: {question}

Sub-questions JSON:"""


SYNTHESIS_PROMPT = """The user asked: {question}

Sub-question results:
{sub_results}

Synthesize a final, concise answer based on the sub-question results."""


@dataclass
class SubQuestionResult:
    """One sub-question's answer."""
    sub_question: str
    answer: str = ""
    error: str = ""


@dataclass
class SubQuestionAnswer:
    """Final answer from SubQuestionQueryEngine."""
    final_answer: str
    original_question: str = ""
    sub_questions: list[SubQuestionResult] = field(default_factory=list)


class SubQuestionQueryEngine:
    """Decompose-then-synthesize engine for complex multi-hop questions.

    Args:
        decomposer_agent: LLM agent that breaks query into sub-questions.
        sub_engine: callable(query) -> answer for each sub-question.
        synthesizer_agent: LLM agent that combines sub-answers.
        max_sub_questions: cap on decomposition.
        max_concurrent: limit on parallel sub-question execution.
    """

    def __init__(
        self,
        *,
        decomposer_agent,
        sub_engine: Callable[[str], "Awaitable[str]"],
        synthesizer_agent,
        max_sub_questions: int = 5,
        max_concurrent: int = 3,
    ):
        self.decomposer = decomposer_agent
        self.sub_engine = sub_engine
        self.synthesizer = synthesizer_agent
        self.max_sub_questions = max_sub_questions
        self.max_concurrent = max_concurrent

    async def _decompose(self, question: str) -> list[str]:
        """Break question into sub-questions via LLM."""
        prompt = DECOMPOSITION_PROMPT.format(question=question)
        try:
            resp = await self.decomposer.run(prompt)
            content = (getattr(resp, "content", "") or "").strip()
            # Strip code fences
            for fence in ["```json", "```"]:
                content = content.replace(fence, "")
            content = content.strip()
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [str(s) for s in parsed[: self.max_sub_questions] if s]
        except Exception as e:
            log.warning(f"decompose failed: {e}")
        return [question]

    async def _run_sub(self, sub_q: str, sem: asyncio.Semaphore) -> SubQuestionResult:
        async with sem:
            try:
                ans = await self.sub_engine(sub_q)
                return SubQuestionResult(sub_question=sub_q, answer=str(ans))
            except Exception as e:
                return SubQuestionResult(sub_question=sub_q, error=str(e))

    async def query(self, question: str) -> SubQuestionAnswer:
        sub_qs = await self._decompose(question)
        if not sub_qs:
            sub_qs = [question]

        sem = asyncio.Semaphore(self.max_concurrent)
        sub_results = await asyncio.gather(
            *[self._run_sub(q, sem) for q in sub_qs]
        )

        # Synthesize
        sub_text = "\n\n".join(
            f"Q: {r.sub_question}\nA: {r.answer or '(error: ' + r.error + ')'}"
            for r in sub_results
        )
        synthesis_prompt = SYNTHESIS_PROMPT.format(
            question=question, sub_results=sub_text,
        )
        try:
            resp = await self.synthesizer.run(synthesis_prompt)
            final = (getattr(resp, "content", "") or "").strip()
        except Exception as e:
            final = f"synthesis failed: {e}"

        return SubQuestionAnswer(
            final_answer=final,
            original_question=question,
            sub_questions=sub_results,
        )


# -------------------- Router Query Engine --------------------

ROUTER_PROMPT = """You are a router. Given a query, choose the SINGLE \
most appropriate engine from the list below.

Available engines:
{engine_descriptions}

Respond with ONLY the engine name on a single line. If no engine fits, \
respond with: DEFAULT

Query: {query}"""


@dataclass
class RouterResult:
    """Result of a RouterQueryEngine.query()."""
    answer: str
    chosen_engine: str
    available_engines: list[str] = field(default_factory=list)


class RouterQueryEngine:
    """Route a query to the most appropriate sub-engine.

    Useful when you have heterogeneous retrieval / answering strategies
    (vector RAG vs SQL agent vs web search) and want the LLM to decide
    which to use for each query.

    Args:
        router_agent: classifier LLM.
        engines: dict of {name: callable(query) -> str}.
        descriptions: dict of {name: description for prompt}.
        default_engine: name of fallback engine if router can't decide.
    """

    def __init__(
        self,
        *,
        router_agent,
        engines: dict[str, Callable[[str], "Awaitable[str]"]],
        descriptions: dict[str, str] | None = None,
        default_engine: str | None = None,
    ):
        if not engines:
            raise ValueError("engines dict cannot be empty")
        self.router = router_agent
        self.engines = engines
        self.descriptions = descriptions or {n: f"the {n} engine" for n in engines}
        self.default_engine = default_engine or next(iter(engines))
        if self.default_engine not in engines:
            raise ValueError(f"default_engine {default_engine!r} not in engines")

    def _format_engines(self) -> str:
        return "\n".join(
            f"- {name}: {self.descriptions.get(name, '')}"
            for name in self.engines
        )

    async def _route(self, query: str) -> str:
        prompt = ROUTER_PROMPT.format(
            engine_descriptions=self._format_engines(), query=query,
        )
        try:
            resp = await self.router.run(prompt)
            choice = (getattr(resp, "content", "") or "").strip().splitlines()
            if not choice:
                return self.default_engine
            chosen = choice[0].strip().rstrip(":,.")
            if chosen.upper() == "DEFAULT" or chosen not in self.engines:
                return self.default_engine
            return chosen
        except Exception as e:
            log.warning(f"router failed: {e}")
            return self.default_engine

    async def query(self, q: str) -> RouterResult:
        chosen = await self._route(q)
        engine = self.engines[chosen]
        try:
            answer = await engine(q)
        except Exception as e:
            answer = f"engine {chosen} failed: {e}"
        return RouterResult(
            answer=str(answer),
            chosen_engine=chosen,
            available_engines=list(self.engines.keys()),
        )
