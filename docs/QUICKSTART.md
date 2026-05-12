# Quickstart

## 1. Create Environment

```bash
python3.12 -m venv .venv-final
. .venv-final/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev,test,rag,guard]'
```

## 2. Run Offline Examples

```bash
python examples/00_offline_test_model.py
python examples/rag_basic/rag_basic.py
```

## 3. Run DeepSeek Examples

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
python examples/01_hello/main.py
python examples/02_tools/main.py
python examples/03_team/main.py
python examples/04_guards/main.py
python examples/05_rag_knowledge/main.py
python examples/10_full_app/main.py
```

If no provider key is set, cloud examples print `SKIP:` with setup instructions and exit cleanly.

## 4. Run Validation

```bash
python -m pytest tests -q --tb=short --disable-warnings -ra --timeout=180 --timeout-method=thread --durations=30
python scripts/smoke_test_e2e.py
scripts/final_release_validate.sh
```
