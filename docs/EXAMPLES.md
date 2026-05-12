# Examples

## Required Examples

| Example | Command | Expected without key | Expected with DeepSeek key |
|---|---|---|---|
| Offline agent | `python examples/00_offline_test_model.py` | PASS | PASS |
| Offline RAG | `python examples/rag_basic/rag_basic.py` | PASS | PASS |
| Hello | `python examples/01_hello/main.py` | SKIP | PASS |
| Tools | `python examples/02_tools/main.py` | SKIP | PASS |
| Team | `python examples/03_team/main.py` | SKIP | PASS |
| Guards | `python examples/04_guards/main.py` | SKIP | PASS |
| RAG knowledge | `python examples/05_rag_knowledge/main.py` | SKIP | PASS |
| Full app | `python examples/10_full_app/main.py` | SKIP | PASS |

Use `timeout 120s python <example>` during release validation. A provider setup error should be a clear `SKIP:` message, not an OpenAI-specific stack trace.
