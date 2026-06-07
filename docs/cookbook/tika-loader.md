# Apache Tika document loader

Apache Tika support is an opt-in parser for broad document extraction in
Largestack AI. Use it when a workflow needs one parser for formats such as
PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, HTML, RTF, and other formats supported by
Apache Tika.

## Tika server backend

Run Apache Tika in a trusted environment, then point Largestack at the server:

```bash
export TIKA_SERVER_URL=http://127.0.0.1:9998
```

```python
from largestack._loaders.tika import load_with_tika

docs = await load_with_tika(
    "file.pdf",
    server_url="http://127.0.0.1:9998",
)
```

The HTTP backend is the default. It uses `/rmeta/text` for recursive metadata
and content extraction, then falls back to `/tika/text` if recursive metadata
is unavailable.

## Dispatcher usage

Use the Tika parser through the loader dispatcher without changing default
loader behavior:

```python
from largestack._loaders import load

docs = await load("file.docx", parser="tika")
```

Calling `load("file.docx")` without `parser="tika"` continues to use the
built-in Largestack loader for that file type.

## Python package backend

The optional Python backend uses the PyPI `tika` package:

```bash
pip install "largestack[tika]"
```

```python
from largestack._loaders.tika import load_with_tika

docs = await load_with_tika("file.pdf", backend="python")
```

This backend may require Java and may start or download Apache Tika server
assets depending on the user environment. Prefer the HTTP server backend for
production and controlled-pilot deployments.

## Security note

Files are sent to the configured Apache Tika server. For production workloads,
run Tika on trusted internal infrastructure, avoid sending sensitive documents
to unknown remote servers, and do not log extracted document content.
