# Fine-Tuning Guide

LARGESTACK does **not** ship a fine-tuning pipeline. This is a deliberate
choice — building one well requires GPU infrastructure, dataset
curation tools, weights & biases integration, and ops you'd rather
borrow than build.

This document points you at the right external tools and shows how to
plug a fine-tuned model back into LARGESTACK.

## When you actually need fine-tuning

Most teams **don't**. Before fine-tuning, try in this order:

1. **Better prompts.** A 200-word prompt with examples often beats
   fine-tuning a smaller model.
2. **RAG.** Retrieve domain knowledge at query time. Cheaper, more
   accurate, easier to update.
3. **Few-shot examples.** Include 5-10 examples in the system prompt.
4. **Use a bigger model.** GPT-4o or Claude Sonnet 4.6 often eliminate
   the need for fine-tuning.

Fine-tune only when:

- You have **>10,000 high-quality examples** of the input/output pattern
  you want.
- The pattern is **stable** — your domain isn't shifting weekly.
- Latency or cost matters enough that running a smaller fine-tuned
  model is worth the engineering investment.
- You've measured that prompts + RAG + bigger models can't get there.

## Recommended tools

### 1. OpenAI / Anthropic / Together hosted fine-tuning

**Easiest path — use this first.**

- OpenAI: <https://platform.openai.com/docs/guides/fine-tuning>
- Together AI: <https://docs.together.ai/docs/fine-tuning-overview>
- Anthropic: contact sales (limited availability).

You upload a JSONL file in the chat-completions format, the platform
trains, you get a model ID. Plug it into LARGESTACK:

```python
from largestack import Agent
agent = Agent(
    name="fine_tuned",
    llm="openai/ft:gpt-4o-mini-2024-07-18:my-org::abc123",
)
```

That's it. **No special LARGESTACK support needed** — fine-tuned models look
like regular models to the API.

### 2. HuggingFace TRL (Transformer Reinforcement Learning)

For fine-tuning open-weight models (Llama, Mistral, Qwen, Gemma, etc.).

- Repo: <https://github.com/huggingface/trl>
- Docs: <https://huggingface.co/docs/trl>

Supports:
- **SFT** (Supervised Fine-Tuning)
- **DPO** (Direct Preference Optimization) — train from human preferences
- **PPO** (Proximal Policy Optimization) — RL fine-tuning
- **LoRA / QLoRA** — parameter-efficient fine-tuning that fits on
  consumer GPUs (12-24GB VRAM is enough for 7B models in 4-bit)

Minimal SFT example (paste this into a HF script, NOT into LARGESTACK):

```python
from trl import SFTTrainer
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-7B")
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B")

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=my_dataset,  # HF Datasets format
    max_seq_length=2048,
)
trainer.train()
trainer.save_model("./my-fine-tuned-model")
```

Then serve via [vLLM](https://github.com/vllm-project/vllm) or
[Ollama](https://ollama.ai/), and point LARGESTACK at it:

```python
agent = Agent(name="ft", llm="ollama/my-fine-tuned-model")
# Or:
agent = Agent(name="ft", llm="openai/my-model",
              base_url="http://localhost:8000/v1")  # vLLM OpenAI-compatible endpoint
```

### 3. Axolotl (config-file driven fine-tuning)

If you don't want to write any Python:

- Repo: <https://github.com/axolotl-ai-cloud/axolotl>
- Define training in a YAML config; `axolotl train config.yml` does
  everything.
- Used by many open-source model releases (e.g. Wizard, Nous-Hermes).

### 4. Unsloth (faster, lower memory)

- Repo: <https://github.com/unslothai/unsloth>
- 2x faster training, 50% less memory than vanilla HF.
- Same API as TRL — drop-in replacement for SFTTrainer.

## Dataset format

All of these tools expect data in JSONL with chat-completion format:

```jsonl
{"messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "What is 2+2?"}, {"role": "assistant", "content": "4"}]}
{"messages": [{"role": "user", "content": "Capital of France?"}, {"role": "assistant", "content": "Paris"}]}
```

LARGESTACK doesn't generate this for you, but you can extract it from your
existing trace database:

```python
import sqlite3, json

# Read LARGESTACK traces
db = sqlite3.connect("~/.largestack/traces.db")
rows = db.execute("SELECT input, output FROM traces WHERE status='completed'").fetchall()

# Convert to JSONL
with open("training_data.jsonl", "w") as f:
    for inp, out in rows:
        rec = {"messages": [
            {"role": "user", "content": inp},
            {"role": "assistant", "content": out},
        ]}
        f.write(json.dumps(rec) + "\n")
```

Filter and curate by hand — quality > quantity. **Aim for 1,000 great
examples, not 10,000 mediocre ones.**

## Why LARGESTACK doesn't ship its own pipeline

A fine-tuning "framework" without:
- Real GPU integration (CUDA, vLLM, deepspeed)
- Dataset versioning (DVC, HF Datasets)
- Experiment tracking (W&B, MLflow)
- Model registry
- Evaluation harness

…is just a wrapper. The wrappers exist (TRL, Axolotl, Unsloth) and they're
better than anything we'd build from scratch. Use them, then plug the
output into LARGESTACK.

## Serving your fine-tuned model

Once you have a checkpoint:

| Serving stack | Use when |
|---|---|
| **Ollama** | Single-user dev, easy to set up. |
| **vLLM** | Production, high throughput, OpenAI-compatible API. |
| **Text Generation Inference (TGI)** | Production, supports more model architectures. |
| **Together AI / Modal / RunPod** | Serverless GPU, you don't manage infra. |

All of these expose an OpenAI-compatible endpoint. Tell LARGESTACK:

```python
import os
os.environ["LARGESTACK_OPENAI_API_KEY"] = "any-string"  # vLLM/Ollama don't check
agent = Agent(
    name="ft",
    llm="openai/my-fine-tuned-model",
    base_url="http://localhost:8000/v1",  # or vLLM/Ollama URL
)
```

## What LARGESTACK does well around fine-tuning

LARGESTACK doesn't train models, but it gives you the **infrastructure**
around them:

- **Cost tracking**: every fine-tuned model call is metered alongside
  hosted-model calls.
- **Guardrails**: the same 15 guardrail layers apply to your custom
  model.
- **Audit trail**: hash-chained logs prove what your model did, when,
  for whom.
- **A/B testing**: use `PromptRegistry.render_with_split()` (v0.6.0)
  to test fine-tuned vs base model on a fraction of traffic.
- **Multi-tenant scoping**: route different tenants to different
  fine-tuned models.

That's the right division of labor.
