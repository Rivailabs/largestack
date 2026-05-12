# Local LLM Usage

LARGESTACK supports local LLMs through two patterns.

## Pattern A — Native Ollama provider, chat-only

Use this when you need local/private chat or RAG without tool calls.

```bash
ollama serve
ollama pull llama3.2
export LARGESTACK_OLLAMA_BASE_URL=http://localhost:11434
```

```python
from largestack import Agent

agent = Agent(
    name="local-chat",
    llm="ollama/llama3.2",
    instructions="Reply concisely.",
    cost_budget=0.0,
)
```

The native `OllamaProvider` is chat-only in this release.

## Pattern B — LiteLLM/OpenAI-compatible local endpoint

Use this when you need a unified gateway across cloud and local models. Tool calling depends on the local model and proxy support.

```bash
pip install largestack[litellm]
# Configure LiteLLM/Ollama according to your proxy setup.
```

```python
from largestack import Agent

agent = Agent(
    name="local-router",
    llm="litellm/ollama/llama3.1",
    instructions="Use the local model.",
)
```

## Production rule

Do not claim local tool automation is production-ready until the exact model, proxy, schema, and tool-calling behavior pass an E2E test.
