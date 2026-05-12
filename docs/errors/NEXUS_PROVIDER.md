# LARGESTACK_PROVIDER — Provider Errors

## LARGESTACK_PROVIDER_TIMEOUT
API didn't respond in time. Increase timeout or add fallback provider.

## LARGESTACK_PROVIDER_AUTH
Invalid API key. Check: `echo $LARGESTACK_OPENAI_API_KEY`

## LARGESTACK_RATE_LIMIT
Provider rate limited. Automatic retry with exponential backoff handles this. If persistent, add a second provider as fallback.

## LARGESTACK_ALL_FAILED
Every provider in the fallback chain failed. Solutions:
1. Check provider status pages
2. Add local fallback: `llm="ollama/llama3"`
3. Check circuit breaker state in dashboard
