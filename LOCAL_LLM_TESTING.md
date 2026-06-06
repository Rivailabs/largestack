# Local LLM — what was tested, and how to reproduce

Verified on this machine on 2026-06-06. Goal: prove largestack runs **fully local, zero cloud, cost=0** end-to-end.

## Environment
- **Ollama v0.30.5** (real binary), GPU-accelerated (NVIDIA RTX 4000 Ada, CUDA).
- Models pulled: **`qwen2.5:0.5b`** (397 MB), **`llama3.2:1b`** (1.3 GB, tool-capable).
- `ollama serve` on `127.0.0.1:11434`.

## Two local routes
| Model string | Endpoint | Tools | Enable |
|---|---|---|---|
| `ollama/<model>` | native `/api/chat` | via `ollama_openai/` | on by default in dev |
| `ollama_openai/<model>` | OpenAI-compat `/v1` | **yes** | `LARGESTACK_OLLAMA_OPENAI_COMPAT=1` |
| `local/<model>` | alias of the above (or `LARGESTACK_OPENAI_COMPATIBLE_BASE_URL`) | yes | — |

> ⚠️ `LARGESTACK_*` env vars are read by a **cached** config singleton — set them **before** the first `Agent`/`get_config()`.

## Results
| Check | Model | Result |
|---|---|---|
| Native chat round-trip | `ollama/qwen2.5:0.5b` | ✅ "Paris", cost=0.0 |
| Tool calling (full round-trip, args typed correctly, tool executed) | `ollama_openai/llama3.2:1b` | ✅ `tool_calls_made=['add']` → 42 |
| Guardrails — prompt-injection blocked | `qwen2.5:0.5b` + `["pii","injection"]` | ✅ blocked (`action=block`) |
| Guardrails — benign allowed | same | ✅ allowed |
| `CodeSandbox` (subprocess) safe / error / infinite-loop | n/a | ✅ exit0 / exit1 / exit124 (10s timeout) |
| `check_connection("ollama/…")` self-test | ollama | ✅ `ok=True`; no-key provider → `ok=False` + exact error |
| **Typed / structured output** | `llama3.2:1b`, `qwen2.5:0.5b` | ❌ **fails on tiny models** (model emits the JSON *schema* / malformed JSON; prompt-fallback can't recover) |

## Honest takeaways
1. **Local chat, tool-calling, guardrails, sandbox, and the connection self-test all work end-to-end, fully offline, at $0 cost.**
2. **Typed/structured output needs a capable model.** 0.5b/1b-class local models are unreliable for it (verified failing here); DeepSeek/Gemini pass. Document the "typed agents" wedge as **model-dependent** — don't imply 1b-class local models give reliable typed output.
3. Tool arguments are **not coerced** to their annotated types (`tools.py:302`). Capable models send correct JSON types; a weak model sending `"19"` for an `int` would concatenate. Latent robustness gap (see `REVIEW_2026-06-06.md` F-ENG-3).

## Reproduce
```bash
ollama serve &                       # 127.0.0.1:11434
ollama pull qwen2.5:0.5b
ollama pull llama3.2:1b
LARGESTACK_OLLAMA_OPENAI_COMPAT=1 .venv/bin/python /tmp/ls_local_verify.py
```
The verification script (`/tmp/ls_local_verify.py`) prints a PASS/FAIL line per check. Matrix status (`provider_matrix.py`) for `ollama`/`ollama_openai` is set to **verified** on the strength of these live runs.
