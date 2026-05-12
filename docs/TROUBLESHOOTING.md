# Troubleshooting

## ProviderError: no provider configured

Set a provider key and model:

```bash
export LARGESTACK_DEEPSEEK_API_KEY=<deepseek-api-key>
export LARGESTACK_DEFAULT_MODEL=deepseek/deepseek-chat
```

Or run the offline quickstart:

```bash
python examples/00_offline_test_model.py
```

## Python Version

Use Python 3.11 or newer. Release validation should prefer Python 3.12.

```bash
.venv-final/bin/python --version
```

## Virtual Environment

If imports fail, reinstall editable dependencies:

```bash
python -m pip install -U pip
python -m pip install -e '.[dev,test,rag,guard]'
```

## DeepSeek Key

Do not paste keys into files or reports. Export the key only in your shell. If the key was pasted into chat or logs, rotate it before release validation.

## Docker Permission Issues

If Docker cleanup or runtime probes fail with permission errors, run cleanup from an admin-enabled shell or ask the host owner to remove stale containers.

## Pytest Timeout

Run with thread timeouts and durations:

```bash
python -m pytest tests -q --tb=short --disable-warnings -ra --timeout=180 --timeout-method=thread --durations=30
```

If a single test hangs, fix the blocking code or gate the external dependency. Do not hide a hang with broad deselection.

## Dashboard Auth

In production, `/health` may be public, but metrics/API endpoints must require the configured key or cookie auth. A wrong key should return `401` or `403`.
