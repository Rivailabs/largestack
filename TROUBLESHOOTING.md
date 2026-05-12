# Troubleshooting

## Installation issues

### `cryptography` not found
```bash
pip install cryptography>=42.0
```

### `httpx[http2]` HTTP/2 errors
```bash
pip install "httpx[http2]"
```

## Runtime errors

### "No provider configured for 'X'"
Configure API key: `export LARGESTACK_<PROVIDER>_API_KEY=...`

### "ProviderError: rate limit"
Reduce `cost_budget` or use `Agent(fallback=other_agent)`.

### "AllProvidersFailedError"
All configured providers failed. Check API keys and connectivity.

### TestModel not found
```python
from largestack.testing import TestModel  # Not from largestack directly
```

## Debug mode

```bash
export LARGESTACK_LOG_LEVEL=DEBUG
export LARGESTACK_LOG_CONTENT=1  # Log prompts (PII risk!)
```

## Get help

- Discord: https://discord.gg/largestack-ai (coming soon)
- GitHub Issues: https://github.com/rivailabs/largestack-agentic-ai/issues
- Email: hello@rivailabs.com
