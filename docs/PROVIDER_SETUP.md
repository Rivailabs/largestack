# Provider Setup

## Default Example Behavior

Examples call `examples/_provider.py`:

1. `LARGESTACK_DEFAULT_MODEL` overrides selection.
2. `LARGESTACK_DEEPSEEK_API_KEY` selects `deepseek/deepseek-chat`.
3. `LARGESTACK_OPENAI_API_KEY` selects `openai/gpt-4o-mini`.
4. Missing keys produce a clean `SKIP:` message.

## DeepSeek

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
export LARGESTACK_DEFAULT_MODEL=deepseek/deepseek-chat
```

Live tests:

```bash
python -m pytest tests/integration/test_deepseek_integration.py tests/integration/test_deepseek_automation.py -q -ra --timeout=180 --timeout-method=thread
```

DeepSeek may not support every native structured-output feature exactly like OpenAI. Provider-incompatible tests should be skipped narrowly with a documented reason; fallback behavior should still be tested.

## OpenAI

```bash
export LARGESTACK_OPENAI_API_KEY=<openai-api-key>
export LARGESTACK_DEFAULT_MODEL=openai/gpt-4o-mini
```

Use OpenAI-specific examples only when OpenAI is the intended provider.

## Ollama

```bash
ollama serve
export LARGESTACK_ENABLE_OLLAMA=1
export LARGESTACK_OLLAMA_BASE_URL=http://localhost:11434
```

Ollama tests should skip when the server is not running.

## LiteLLM

Use `litellm/provider-model` style routes where supported by the router and configure the underlying provider key expected by LiteLLM.

## Secret Handling

Never commit `.env`, never print keys in logs, and rotate any key pasted into chat, shell history, or reports.
