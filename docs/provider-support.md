# Provider Support Matrix

LARGESTACK separates **adapter exists** from **verified production support**.
Use `largestack.provider_support_matrix()` to inspect capabilities at runtime.

Status meanings:

- `verified`: covered by local tests and known primary implementation path.
- `partial`: adapter and routing exist, but exact tool/structured-output behavior depends on the provider/model or live credentials.
- `experimental`: useful path, but must be live-tested before production claims.
- `adapter_only`: source adapter exists, but should not be marketed until wired and verified.

Public proof tiers:

- `validated`: verified path with local tests and release evidence.
- `compatible`: adapter or OpenAI-compatible path exists; require model-specific live E2E before strong claims.
- `experimental`: useful but not production-claimable yet.
- `skipped`: adapter/source exists, but omit from marketing until wired and validated.

## Recommended production claim

Say:

> LARGESTACK supports OpenAI, DeepSeek, Anthropic, LiteLLM, Ollama/local models, and many OpenAI-compatible providers through a verified/partial capability matrix.

Do not say every listed provider has equal production-grade tool-calling support until live E2E gates pass.

## Public Provider Proof Register

This table is the public claim source. Keep it aligned with
`largestack.provider_support_matrix()`.

| Provider | Public tier | Current proof | Next gate before stronger claim |
|---|---|---|---|
| OpenAI | validated | Primary adapter path and local tests | Fresh live E2E for chosen public model |
| DeepSeek | validated | Live difficult-project evidence plus OpenAI-compatible path | Repeat on release branch with current key |
| Anthropic | validated | Native adapter and tool mapping tests | Fresh live E2E for chosen Claude model |
| LiteLLM | compatible | Gateway integration present | Per-downstream-provider live E2E |
| local OpenAI-compatible | compatible | Generic OpenAI-compatible path | Validate target runtime/model tool behavior |
| Ollama native | compatible | Native chat path | Tool/structured output proof via compatible path |
| Ollama OpenAI-compatible | experimental | `/v1` compatible path present | Model/runtime tool-call validation |
| Google/Gemini | compatible | Chat adapter present | First-class tools/structured-output E2E |
| Groq | compatible | OpenAI-compatible path | Model-specific tool/structured-output E2E |
| Mistral | compatible | OpenAI-compatible path | Model-specific tool/structured-output E2E |
| Cohere | compatible | Chat/embedding adapter present | Tool parsing and streaming proof |
| Bedrock | compatible | Adapter present, AWS credential gated | AWS live E2E and error/fallback proof |
| Azure OpenAI | compatible | Azure OpenAI-compatible path | Deployment-specific live E2E |
| OpenRouter | compatible | Aggregator path present | Routed-model proof for claimed model |
| Perplexity | compatible | Chat/research path present | Tool/structured-output proof if claimed |
| Cerebras | compatible | OpenAI-compatible path | Live model-specific E2E |
| SambaNova | compatible | OpenAI-compatible path | Live model-specific E2E |
| xAI | compatible | OpenAI-compatible path | Live model-specific E2E |
| AI21 | compatible | Adapter present | Live chat/tool capability proof |
| Lepton | compatible | OpenAI-compatible path | Live model-specific E2E |
| NVIDIA | compatible | OpenAI-compatible path | Live model-specific E2E |
| Anyscale | skipped | Adapter source exists | Wire into release gate before listing publicly |
| Cloudflare | skipped | Adapter source exists | Wire into release gate before listing publicly |
| Databricks | skipped | Adapter source exists | Workspace auth/live E2E |
| Replicate | skipped | Adapter source exists | Live chat path and error handling proof |
| Voyage | skipped | Embeddings-oriented adapter | Do not market as chat-provider support |

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
