# Jarvis — a working DEMO assistant on Largestack

A small but **real** personal assistant (not design docs) built on the
[Largestack](https://pypi.org/project/largestack/) framework. It has persistent
memory, real tools, PII + injection guardrails, cost tracking, and human-approval
gating for risky actions.

> **This is a demo / starter bundle, not a production product.** It uses Largestack's
> stable `Agent` API. For a production build, migrate to the typed decorator API
> (`largestack.decorators.Agent`) per `AGENTS.md`. Requires **largestack ≥ 1.1.0**.

## Quick start

```bash
# 1. install
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. set a provider key (DeepSeek by default)
export LARGESTACK_DEEPSEEK_API_KEY="sk-..."

# 3. run
python run.py --demo          # scripted tour of every feature
python run.py                 # interactive chat
python run.py --once "Take a note: water the plants"
```

## What it does
| Feature | Tool | Real? |
|---|---|---|
| Notes | `take_note`, `list_notes` | ✅ persisted to `~/.jarvis/notes.json` |
| Memory of facts | `remember_fact`, `recall_fact` | ✅ persisted to `~/.jarvis/facts.json` |
| Math | `calculate` | ✅ safe, **bounded** arithmetic (rejects huge/`**` DoS inputs) |
| Files | `list_directory` | ✅ read-only, **confined to the workspace** (`JARVIS_WORKSPACE`) |
| Self Q&A | `search_knowledge` | ✅ keyword search over `knowledge/` |
| Risky actions | `request_approval` | ✅ **gated + persisted** to `~/.jarvis/approvals.json`; never executed |

## Project layout
```
jarvis_app/
  run.py                 # entry point (interactive / --demo / --once)
  jarvis/
    assistant.py         # the Largestack Agent + guardrails + system prompt
    tools.py             # the real tools the agent can call
    memory_store.py      # persistent notes + facts (JSON on disk)
    config.py            # model, budgets, data dir
  knowledge/about.md     # documents Jarvis can answer from
  test_jarvis.py         # focused tests (no API key needed)
  requirements.txt
```

## Test it (no API key)
```bash
python -m pytest test_jarvis.py -q
```

## Notes
- Default model is DeepSeek; set `LARGESTACK_DEFAULT_MODEL=openai/gpt-4o-mini`
  (+ `LARGESTACK_OPENAI_API_KEY`) to switch providers.
- Each request is capped by `JARVIS_COST_BUDGET` (default $0.50) and `retries=2`.
- `list_directory` is confined to `JARVIS_WORKSPACE` (default: the launch dir).
- `request_approval` only ever *records* a pending request — it never executes anything.
- This is a starting point — extend `tools.py` with your own real integrations.
