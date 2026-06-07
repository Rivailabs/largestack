# Installation

Largestack AI is a Beta Python framework. Requires **Python >= 3.11** (3.11 / 3.12 / 3.13).

```bash
python -m pip install -U pip
pip install largestack
```

- PyPI: <https://pypi.org/project/largestack/>
- GitHub: <https://github.com/Rivailabs/largestack>

---

## Verify the install

```bash
largestack --help
largestack version          # -> Largestack AI v1.1.1
```

```python
import largestack
print(largestack.__version__)   # 1.1.1
```

---

## Optional extras

Core install is provider-agnostic (it talks to OpenAI-compatible HTTP endpoints out
of the box). Install extras for native SDKs and heavier features:

```bash
pip install "largestack[openai]"           # one extra
pip install "largestack[openai,rag,guard]" # several
```

| Extra | Pulls in |
|---|---|
| `openai` | `openai`, `tiktoken` |
| `anthropic` | `anthropic` |
| `litellm` | `litellm`, `aiohttp` (multi-provider gateway) |
| `mcp` | `fastapi`, `uvicorn` (serve MCP) |
| `rag` | `sentence-transformers`, `faiss-cpu`, `qdrant-client`, `duckdb`, `beautifulsoup4` |
| `guard` | `presidio-analyzer`, `presidio-anonymizer` (PII guardrails) |
| `otel` | OpenTelemetry API + SDK |
| `office` | `openpyxl`, `python-pptx`, `pandas` |
| `tika` | `tika` (Apache Tika document parsing) |
| `postgres` | `psycopg`, `sqlalchemy` |
| `migrations` | `alembic`, `sqlalchemy` |
| `dev-server` | `fastapi`, `uvicorn`, `watchfiles` (hot-reload dev server) |
| `test` | `pytest`, `pytest-asyncio`, `pytest-timeout`, `hypothesis`, `respx`, `pytest-cov` |
| `docs` | `mkdocs-material`, `pymdown-extensions`, `mkdocstrings` |
| `all` | Everything above (except `docs`) |
| `dev` | `all` + `ruff`, `mypy` |

```bash
pip install "largestack[all]"   # all optional features
pip install "largestack[dev]"   # contributor toolchain
```

> If PyTorch tries to install large CUDA packages on Linux, prefer CPU wheels:
> `PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu pip install "largestack[rag]"`

---

## Provider API keys

Set keys as environment variables using the pattern `LARGESTACK_<PROVIDER>_API_KEY`
(provider name upper-cased). Never commit keys.

```bash
export LARGESTACK_OPENAI_API_KEY="sk-..."
export LARGESTACK_DEEPSEEK_API_KEY="sk-..."
export LARGESTACK_ANTHROPIC_API_KEY="sk-ant-..."
```

The model string selects the provider, e.g. `Agent(name="r", llm="deepseek/deepseek-chat")`.
For local / OpenAI-compatible endpoints, see [local LLMs](local-llm.md) and the
[provider support matrix](provider-support.md).

You can develop and test **without any key** using `TestModel` / `FunctionModel`:

```python
from largestack import Agent
from largestack.testing import TestModel

agent = Agent(name="r", llm="deepseek/deepseek-chat")
# with agent.override(model=TestModel(custom_output_text="canned")):
#     result = await agent.run("anything")   # no network, no key
```
