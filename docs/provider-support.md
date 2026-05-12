# Provider Support Matrix

LARGESTACK separates **adapter exists** from **verified production support**.
Use `largestack.provider_support_matrix()` to inspect capabilities at runtime.

Status meanings:

- `verified`: covered by local tests and known primary implementation path.
- `partial`: adapter and routing exist, but exact tool/structured-output behavior depends on the provider/model or live credentials.
- `experimental`: useful path, but must be live-tested before production claims.
- `adapter_only`: source adapter exists, but should not be marketed until wired and verified.

## Recommended production claim

Say:

> LARGESTACK supports OpenAI, DeepSeek, Anthropic, LiteLLM, Ollama/local models, and many OpenAI-compatible providers through a verified/partial capability matrix.

Do not say every listed provider has equal production-grade tool-calling support until live E2E gates pass.

## Local LLM guidance

- `ollama/<model>`: native Ollama chat path. Good for local chat/summarization.
- `local/<model>` with `LARGESTACK_OPENAI_COMPATIBLE_BASE_URL`: generic OpenAI-compatible endpoint, good for vLLM, LM Studio, Ollama `/v1`, or enterprise gateways.
- `ollama_openai/<model>` with `LARGESTACK_OLLAMA_OPENAI_COMPAT=true`: Ollama OpenAI-compatible endpoint. Tool calling only works if the local runtime/model supports it.

```bash
export LARGESTACK_OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1
export LARGESTACK_OPENAI_COMPATIBLE_API_KEY=ollama
```

```python
from largestack import Agent
agent = Agent(name="local", llm="local/llama3.2")
```
