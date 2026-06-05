# Installation

Install on Python 3.11 or newer. For full validation, prefer Python 3.12, install optional extras with `pip install -e .[all]`, and add `respx pytest-timeout python-pptx pandas beautifulsoup4 duckdb faiss-cpu qdrant-client` when testing loaders, mocked integrations, and vector stores locally.

Apache Tika HTTP server parsing works through the core HTTP dependency. For
the explicit Python package backend, install:

```bash
pip install "largestack[tika]"
```

Use production secrets through environment variables or a managed vault; do not commit API keys.
