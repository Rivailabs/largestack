# LARGESTACK_CONTEXT — Context Window Exceeded

**Error:** `ContextWindowExceededError`  
**Retryable:** No

**When:** The total tokens (system prompt + conversation + tool results) exceed the model's maximum context window.

**Example:**
```
Sent 135,000 tokens but gpt-4o-mini max is 128,000 (7,000 over)
  Suggestion: Use a larger model or enable compression: memory.compression=True
```

**Solutions:**

1. **Enable compression:** Set `context_compression: true` in `largestack.yaml` — extractive summarization reduces context by 3-5x
2. **Use larger context model:** `llm="anthropic/claude-opus-4-6"` (200K) or `llm="openai/gpt-5.2"` (128K)
3. **Sliding window memory:** `ConversationMemory(strategy="sliding_window", max_messages=20)`
4. **Token-limited memory:** `ConversationMemory(strategy="token_limited", max_tokens=4000)`
5. **Reduce tool output:** Truncate tool results in your tool functions — return summaries not full documents
