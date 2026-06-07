# RAG

The RAG release gate covers recall@k, MRR, citation presence, no-answer behavior, tenant filtering, table/BOM retrieval, large corpus retrieval, and rerank non-regression. Vector-store validation includes in-memory, FAISS, DuckDB, and Qdrant when the optional SDK/service is available.

For broad enterprise document extraction, Largestack can use Apache Tika as an
opt-in parser via `load_with_tika()` or `load(path, parser="tika")`. Tika is
useful for PDF, DOC/DOCX, PPT/PPTX, XLS/XLSX, HTML, RTF, and other supported
formats when a trusted Tika server is available.

## Maturity Boundaries

Do not market RAG as fully enterprise-hardened until these gates have fresh
release evidence:

| Area | Current public claim | Required hardening proof |
|---|---|---|
| Retrieval | Local retrieval works with evaluation coverage | Production-scale corpus benchmark with latency and recall targets |
| Reranking | Rerank path exists | Non-regression benchmark across representative corpora |
| Citation confidence | Citation presence is tested | Confidence calibration against labeled answer/citation pairs |
| Tenant filtering | Tenant-aware paths exist | Cross-tenant leakage tests for every persistent vector backend |
| Metadata indices | Metadata filters are supported in selected paths | Backend-specific index/filter validation at scale |
| GraphRAG | Experimental/conceptual | Real graph construction, query tests, and failure-mode docs |
