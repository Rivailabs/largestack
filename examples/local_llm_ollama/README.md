# Local LLM via Ollama

Run a LARGESTACK agent against a local Ollama-served model — zero cloud cost, full data residency.

## Setup

1. Install [Ollama](https://ollama.com/download) and pull a tool-capable model:
   ```bash
   ollama pull llama3.1:70b      # recommended for tool calling
   # OR (smaller, but tool calling is ~70% reliable):
   ollama pull llama3.1:8b
   ```

2. Verify Ollama is running:
   ```bash
   curl http://localhost:11434/v1/models
   ```

3. Set environment so LARGESTACK uses the local endpoint:
   ```bash
   export LARGESTACK_OLLAMA_BASE_URL="http://localhost:11434/v1"
   export OPENAI_API_KEY="ollama"   # any non-empty string
   ```

4. Run:
   ```bash
   python agent.py
   ```

## Why a 70B+ model for tools

Below 8B parameters, function/tool calling fails ~30% of the time. Llama 3.1 70B
or Mixtral 8x7B is the practical floor for production tool agents. For chat-only
agents (no `tools=`), 8B is fine.

## Files

- `agent.py` — minimal agent that uses a local model + one tool.
- `chat_only.py` — chat-only variant that runs reliably on smaller models.
