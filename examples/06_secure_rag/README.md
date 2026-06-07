# 06 — Secure RAG agent

One composable, **safe-by-default** pipeline for putting an agent in front of real users.
`SecureRAGAgent` chains the building blocks largestack already ships:

```
user query
  → RBAC gate (optional)        # caller must hold the required permission
  → input guardrails            # PII + prompt-injection, pre-retrieval
  → hybrid retrieval            # BM25 (+ dense vector when dense=True / embed_fn=)
  → reranker (optional)
  → trusted chunks              # grounded context only
  → LLM (cost budget)           # largestack.Agent: input/output guardrails, OTel span, trace + audit
  → output guardrails
  → groundedness evaluation     # faithfulness of the answer vs the retrieved chunks
  → citation validation         # map answer sentences → sources
  → SecureRagResult
```

## Run

```bash
ollama pull llama3.2:1b      # local, $0 — or use any provider, e.g. deepseek/deepseek-chat
python main.py
```

```python
from largestack import SecureRAGAgent
from largestack._enterprise.rbac import RBAC

rbac = RBAC(); rbac.add_role("agent", ["rag.query"]); rbac.add_user("alice", roles=["agent"])
rag = SecureRAGAgent(docs, llm="ollama/llama3.2:1b", rbac=rbac)

res = await rag.answer("What is our refund window?", user_id="alice")
res.answer          # cited answer
res.grounded        # bool — groundedness >= threshold
res.citations       # [{sentence, sources, confidence}, ...]
res.cost, res.trace_id
res.allowed, res.denied_reason, res.blocked_by_guardrail
```

`SecureRagResult` is always returned (policy decisions don't raise): RBAC denials set
`allowed=False`; a tripped guardrail sets `blocked_by_guardrail`.

## Deliberately out of scope (add at your deployment seam)
- **Vector DB (Qdrant/etc.):** start with `dense=True` (local sentence-transformers) or
  pass your own `embed_fn`; swap the store via `largestack._vectorstores` when you outgrow it.
- **SIEM export:** every run writes an audit row (`~/.largestack/audit.db`) — add a thin
  `audit → syslog/CEF/webhook` exporter for your SIEM.
- **LangSmith:** the engine already emits Phoenix/OTel traces.
