# GitHub repository settings

Run after final security review:

```bash
gh repo edit Rivailabs/largestack \
  --description "Python framework for typed agents, tools, RAG, guardrails, observability, and orchestration" \
  --homepage "https://largestack.ai" \
  --add-topic ai \
  --add-topic agents \
  --add-topic llm \
  --add-topic rag \
  --add-topic guardrails \
  --add-topic observability \
  --add-topic multi-agent \
  --add-topic python \
  --add-topic agentic-ai \
  --enable-issues \
  --enable-discussions
```

Make public only after final secrets review:

```bash
gh repo edit Rivailabs/largestack \
  --visibility public \
  --accept-visibility-change-consequences
```
