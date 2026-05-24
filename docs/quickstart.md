# Quickstart

This guide takes a beginner from clone to first validation.

---

## Requirements

| Tool | Required |
|---|---|
| Python | 3.11+ recommended, 3.12 preferred |
| Git | Yes |
| Docker | Optional but recommended |
| DeepSeek/OpenAI key | Optional for live provider tests |

---

## 1. Clone

```bash
# Public GitHub clone URL should be added after repository visibility is enabled.
cd largestack
```

---

## 2. Create virtual environment

Linux/macOS:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -3.12 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
```

---

## 3. Install

```bash
python -m pip install -U pip setuptools wheel
python -m pip install -e ".[dev]"
```

If PyTorch tries to install large CUDA packages on Linux, use CPU wheels:

```bash
PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
python -m pip install -e ".[dev]"
```

---

## 4. First test

```bash
python -m pytest tests/unit/test_memory.py -q --tb=short
```

Expected:

```text
10 passed
```

---

## 5. Compile check

```bash
python -m compileall largestack tests examples scripts
```

This catches syntax/import-path problems early.

---

## 6. Full test suite

```bash
python -m pytest tests -q --tb=short -ra
```

Live DeepSeek tests run only when `LARGESTACK_DEEPSEEK_API_KEY` is set.

---

## 7. Live DeepSeek check

```bash
export LARGESTACK_DEEPSEEK_API_KEY="your_key_here"
python -m pytest tests/integration/test_deepseek_integration.py -q --tb=short -ra
```

Never commit keys.

---

## 8. Docker health check

```bash
docker build -t largestack:test .
docker run --rm -d --name largestack-test -p 8787:8787 largestack:test
curl http://127.0.0.1:8787/health
docker rm -f largestack-test
```

Expected health response should show an OK/healthy status.
