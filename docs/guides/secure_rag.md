# Secure RAG agent

`SecureRAGAgent` composes the safety layers into one pipeline so you can put a RAG
agent in front of real users without wiring each guard yourself:

```
query → RBAC gate → input guardrails (PII + injection) → hybrid retrieval (+ rerank)
      → trusted chunks → LLM (cost budget) → output guardrails → groundedness eval
      → citation validation → output sanitization → OTel trace + audit row → result
```

```python
from largestack import SecureRAGAgent

rag = SecureRAGAgent(
    ["Refunds are available within 30 days of purchase.",
     "Warranty covers manufacturing defects for 12 months."],
    llm="deepseek/deepseek-chat",   # or "ollama/llama3.2:1b" for local/offline
    cost_budget=0.05,
)
res = await rag.answer("What is the refund window?")
print(res.answer)        # grounded, cited answer
print(res.grounded, res.citations, res.cost, res.trace_id)
```

`answer()` always returns a `SecureRagResult` — policy decisions never raise:

| Field | Meaning |
|---|---|
| `answer` | the (sanitized, cited) answer text |
| `allowed` / `denied_reason` | RBAC outcome (False + reason if the caller lacks permission) |
| `blocked_by_guardrail` | set if an input/output guard blocked the request |
| `grounded` / `groundedness` | faithfulness of the answer vs the retrieved chunks |
| `citations` / `sources` | per-sentence citations and the cited sources |
| `sanitized` | True if output sanitization altered the answer |
| `cost` / `trace_id` | per-query cost and the trace id |

## RBAC gating

Pass any object exposing `check(user_id, permission) -> bool` (e.g. the built-in RBAC):

```python
from largestack._enterprise.rbac import RBAC
rbac = RBAC(); rbac.add_role("support", ["rag.query"]); rbac.add_user("alice", roles=["support"])

rag = SecureRAGAgent(docs, llm="deepseek/deepseek-chat", rbac=rbac, required_permission="rag.query")
denied = await rag.answer("…", user_id="eve")     # allowed=False, no LLM call, audited
ok     = await rag.answer("…", user_id="alice")    # runs the full pipeline
```

## Options

| Arg | Default | Notes |
|---|---|---|
| `guardrails` | `("pii", "injection")` | guard names; run pre-retrieval and at the LLM step |
| `dense` / `embed_fn` | `False` | `dense=True` (local sentence-transformers) or a sync `embed_fn` enables hybrid BM25+dense retrieval |
| `reranker` | `None` | pass a `Reranker` to rerank candidates |
| `cost_budget` | `0.5` | per-query USD ceiling |
| `groundedness_threshold` | `0.5` | min faithfulness to mark `grounded=True` |
| `sanitize_output` | `True` | strip active HTML/script from the answer before returning |
| `audit` | `True` | write RBAC-deny / guard-block events to the audit trail |

## Deliberately not auto-wired (documented seams)
- **Vector DB (Qdrant/etc.):** start with `dense=True` or your own `embed_fn`; swap the
  store via `largestack._vectorstores` when you outgrow in-memory/BM25.
- **SIEM export:** every run writes an audit row — use `largestack siem-export` for your SIEM.
- **LangSmith:** the engine emits Phoenix/OTel traces; LangSmith is not bundled.

See also: [Guardrails](../concepts/guardrails.md) · [OWASP coverage & red-team](../owasp-coverage.md) · [RAG](../rag.md).
