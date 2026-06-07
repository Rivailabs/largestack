"""Secure RAG agent — one composable, safe-by-default pipeline.

Chains the building blocks largestack already ships into a single, tested flow for
"an agent you can put in front of real users":

    user query
      → RBAC gate                 (optional; you pass an object with .check(user, perm))
      → input guardrails          (PII + prompt-injection, pre-retrieval)
      → hybrid retrieval          (BM25, + dense when dense=/embed_fn= given)
      → reranker                  (optional)
      → trusted chunks            (grounded context only)
      → LLM with cost budget      (largestack.Agent — also runs input/output guardrails,
                                    opens an OTel span, writes the trace + audit row)
      → output guardrails
      → groundedness evaluation   (HallucinationGuard faithfulness vs the chunks)
      → citation validation       (CitationEngine maps sentences → sources)
      → SecureRagResult

NOT included by design (add when a real deployment needs them — see the Secure RAG guide):
  - A specific vector DB (Qdrant/etc.): pass dense=True (local) or your own embed_fn;
    swap the store via largestack._vectorstores when you outgrow in-memory/BM25.
  - SIEM export: the run already writes an audit row (~/.largestack/audit.db); add a
    thin audit→syslog/CEF/webhook exporter at your SIEM seam.
  - LangSmith: use the Phoenix/OTel tracing the engine already emits.

Example::

    from largestack.secure_rag import SecureRAGAgent
    rag = SecureRAGAgent(docs, llm="ollama/llama3.2:1b")
    res = await rag.answer("What is our refund window?", user_id="alice")
    print(res.answer, res.grounded, res.citations, res.cost, res.trace_id)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger("largestack.secure_rag")


class SecureRagResult(BaseModel):
    """Structured outcome of a secure RAG query (never raises for policy decisions)."""

    answer: str = ""
    allowed: bool = True  # passed RBAC
    denied_reason: str | None = None  # set when RBAC blocked
    blocked_by_guardrail: str | None = None  # set when an input/output guard blocked
    grounded: bool = False  # groundedness >= threshold
    groundedness: float = 0.0  # faithfulness of answer vs retrieved chunks
    citations: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    cost: float = 0.0
    trace_id: str | None = None
    sanitized: bool = False  # True if output sanitization altered the answer


class SecureRAGAgent:
    """Compose RBAC + guardrails + hybrid RAG + grounded LLM + citations + tracing.

    Args:
      documents: corpus to index (chunked + BM25, + dense if ``dense``/``embed_fn``).
      llm: model string (e.g. ``"ollama/llama3.2:1b"``, ``"deepseek/deepseek-chat"``).
      rbac: optional object exposing ``check(user_id, permission) -> bool`` (e.g.
        ``largestack._enterprise.rbac.RBAC``). If set, ``answer(..., user_id=)`` is gated.
      required_permission: permission the caller must hold (default ``"rag.query"``).
      guardrails: guard names for the LLM step (default ``("pii", "injection")``); the
        same guards run as a pre-retrieval input check.
      dense / embed_fn / reranker: enable hybrid dense retrieval + reranking.
      cost_budget: per-query cost ceiling (USD).
      groundedness_threshold: min faithfulness to mark ``grounded=True``.
      audit: write RBAC-deny / guard-block events to the audit trail (the LLM run is
        already audited by the engine).
    """

    def __init__(
        self,
        documents: list[str] | None = None,
        *,
        llm: str | None = None,
        instructions: str | None = None,
        rbac: Any = None,
        required_permission: str = "rag.query",
        guardrails: tuple[str, ...] = ("pii", "injection"),
        top_k: int = 5,
        dense: bool = False,
        embed_fn: Any = None,
        reranker: Any = None,
        cost_budget: float = 0.5,
        groundedness_threshold: float = 0.5,
        audit: bool = True,
        sanitize_output: bool = True,
    ):
        from largestack import Agent
        from largestack.rag import create_rag
        from largestack._core.citation_sandbox import CitationEngine
        from largestack._guard.hallucination import HallucinationGuard
        from largestack._guard.pipeline import GuardrailPipeline
        from largestack._guard.pii import PIIGuard
        from largestack._guard.injection import InjectionGuard
        from largestack._guard.output_sanitizer import OutputSanitizer

        self.rbac = rbac
        self.required_permission = required_permission
        self.groundedness_threshold = groundedness_threshold
        self._audit_enabled = audit
        # v1.1.1: safe-by-default — sanitize the answer (strip script/iframe/JS-URI)
        # before returning, so the wedge doesn't rely on the caller remembering to.
        self._sanitizer = OutputSanitizer() if sanitize_output else None

        self._rag = create_rag(
            documents or [], top_k=top_k, dense=dense, embed_fn=embed_fn, reranker=reranker
        )
        self._agent = Agent(
            name="secure-rag",
            instructions=instructions
            or (
                "Answer the user's question using ONLY the provided sources. "
                "If the sources are insufficient, say so plainly. Be concise."
            ),
            llm=llm,
            guardrails=list(guardrails),
            cost_budget=cost_budget,
        )
        # Pre-retrieval input guard pass (defense-in-depth; matches the diagram's
        # "input guardrails → PII → injection → retrieval" ordering).
        _pre = []
        if "pii" in guardrails:
            _pre.append(PIIGuard(action="redact"))
        if "injection" in guardrails:
            _pre.append(InjectionGuard())
        self._input_guards = GuardrailPipeline(guards=_pre) if _pre else None
        self._citer = CitationEngine()
        self._grounder = HallucinationGuard(mode="fast")

    def index(self, documents: list[str]) -> None:
        """(Re)ingest documents into the retriever."""
        self._rag.ingest(documents)

    async def aclose(self) -> None:
        await self._agent.aclose()

    def _audit(self, event_type: str, action: str, user_id: str, detail: str) -> None:
        if not self._audit_enabled:
            return
        try:
            from largestack._core.engine import _get_audit

            a = _get_audit()
            if a:
                a.log(
                    event_type,
                    action,
                    agent_name="secure-rag",
                    user_id=user_id or "",
                    details={"detail": detail[:200]},
                )
        except Exception as e:  # never let auditing break the request
            log.debug(f"secure_rag audit failed: {e}")

    async def answer(self, query: str, *, user_id: str | None = None) -> SecureRagResult:
        from largestack.errors import GuardrailBlockedError

        # 1. RBAC gate
        if self.rbac is not None:
            if not user_id or not self.rbac.check(user_id, self.required_permission):
                self._audit("secure_rag.denied", self.required_permission, user_id or "", query)
                return SecureRagResult(
                    allowed=False,
                    denied_reason=f"User '{user_id}' lacks permission '{self.required_permission}'.",
                    answer="PERMISSION DENIED.",
                )

        # 2. Pre-retrieval input guardrails (PII + injection) on the raw query
        if self._input_guards is not None:
            try:
                await self._input_guards.check_input([{"role": "user", "content": query}])
            except GuardrailBlockedError as e:
                gt = getattr(e, "guard_type", "guardrail")
                self._audit("secure_rag.blocked", gt, user_id or "", query)
                return SecureRagResult(
                    allowed=True,
                    blocked_by_guardrail=gt,
                    answer="Request blocked by input guardrails.",
                )

        # 3. Hybrid retrieval (+ rerank) → trusted chunks
        chunks = self._rag.retrieve(query)
        docs = [{"content": c["text"], "id": str(c.get("index", i))} for i, c in enumerate(chunks)]
        context = "\n\n".join(f"[Source {i + 1}] {c['text']}" for i, c in enumerate(chunks))
        if not chunks:
            context = "(no relevant sources found)"

        prompt = (
            f"Sources:\n{context}\n\n"
            f"Question: {query}\n\n"
            "Answer using ONLY the sources above. If they are insufficient, say so."
        )

        # 4. LLM step — input/output guardrails, cost budget, OTel span, trace + audit row
        try:
            result = await self._agent.run(prompt)
        except GuardrailBlockedError as e:
            gt = getattr(e, "guard_type", "guardrail")
            return SecureRagResult(
                allowed=True,
                blocked_by_guardrail=gt,
                answer="Response blocked by output guardrails.",
            )

        answer = result.content or ""

        # 5. Groundedness evaluation + citation validation against the trusted chunks
        try:
            groundedness = float(self._grounder.analyze(answer, context).get("faithfulness", 0.0))
        except Exception:
            groundedness = 0.0
        cited_text, citations, sources = answer, [], []
        if docs and answer:
            try:
                cited = self._citer.cite(answer, docs)
                cited_text = cited.text_with_citations or answer
                citations = [
                    {
                        "sentence": c.sentence,
                        "sources": c.source_doc_indices,
                        "confidence": round(c.confidence, 3),
                    }
                    for c in cited.citations
                ]
                sources = cited.sources
            except Exception as e:
                log.debug(f"secure_rag citation failed: {e}")

        # Safe-by-default output sanitization (strip active content from the answer)
        sanitized = False
        if self._sanitizer is not None and cited_text:
            cleaned = self._sanitizer.sanitize(cited_text, mode="text")
            sanitized = cleaned != cited_text
            cited_text = cleaned

        return SecureRagResult(
            answer=cited_text,
            allowed=True,
            grounded=groundedness >= self.groundedness_threshold,
            groundedness=round(groundedness, 3),
            citations=citations,
            sources=sources,
            cost=float(getattr(result, "total_cost", 0.0) or 0.0),
            trace_id=getattr(result, "trace_id", None),
            sanitized=sanitized,
        )
