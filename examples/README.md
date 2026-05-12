# LARGESTACK Examples

Examples are designed to be runnable from the repository root.

## Offline Quickstart

```bash
python examples/00_offline_test_model.py
python examples/rag_basic/rag_basic.py
```

These do not require a provider key.

## Cloud Examples

Cloud examples use `examples/_provider.py`:

1. `LARGESTACK_DEFAULT_MODEL` wins when set.
2. Otherwise `LARGESTACK_DEEPSEEK_API_KEY` selects `deepseek/deepseek-chat`.
3. Otherwise `LARGESTACK_OPENAI_API_KEY` selects `openai/gpt-4o-mini`.
4. If no key exists, the example exits with `SKIP:` and a setup hint.

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
python examples/01_hello/main.py
python examples/02_tools/main.py
python examples/03_team/main.py
python examples/04_guards/main.py
python examples/05_rag_knowledge/main.py
python examples/10_full_app/main.py
```

## Example Index

| Path | Purpose | Key needed |
|---|---|---|
| `00_offline_test_model.py` | deterministic agent quickstart | no |
| `rag_basic/rag_basic.py` | offline vector search and citations | no |
| `01_hello/main.py` | basic provider-backed agent | DeepSeek/OpenAI |
| `02_tools/main.py` | tool calling | DeepSeek/OpenAI |
| `03_team/main.py` | multi-agent/team flow | DeepSeek/OpenAI |
| `04_guards/main.py` | guardrails | DeepSeek/OpenAI |
| `05_rag_knowledge/main.py` | tool-backed knowledge/RAG pattern | DeepSeek/OpenAI |
| `06_streaming/main.py` | streaming output | DeepSeek/OpenAI |
| `07_structured/main.py` | typed structured output | DeepSeek/OpenAI; provider compatibility may vary |
| `09_multi_provider/main.py` | fallback wiring | DeepSeek/OpenAI |
| `10_full_app/main.py` | typed agent + RAG + tool pattern | DeepSeek/OpenAI |

No example should print or persist API keys.
