"""Advanced retrieval patterns (v0.7.0).

Three production-grade retrieval techniques that meaningfully improve
RAG quality over naive vector search:

1. **Multi-Query Retrieval** — LLM rewrites the query into N variants;
   union the results. Catches cases where the user's phrasing misses
   relevant documents indexed under different wording.

2. **HyDE (Hypothetical Document Embeddings)** — LLM generates a
   plausible answer to the query, then embeds THAT and retrieves docs
   near it. Often outperforms direct query embedding because the
   answer's semantic signature is closer to relevant docs than the
   question's signature.

3. **Reciprocal Rank Fusion (RRF)** — combines results from multiple
   retrievers using rank-position rather than score, robust to score
   distribution differences. The standard fusion technique used in
   hybrid search systems.

Reference papers:
- Multi-Query: implementations across LangChain/LlamaIndex
- HyDE: Gao et al. "Precise Zero-Shot Dense Retrieval without
  Relevance Labels" (https://arxiv.org/abs/2212.10496)
- RRF: Cormack et al. "Reciprocal rank fusion outperforms condorcet
  and individual rank learning methods" (SIGIR 2009)

Usage:

    from largestack._retrievers import multi_query_retrieve, hyde_retrieve, rrf_fuse

    # Multi-query: 1 query → N variants → 1 fused result list
    results = await multi_query_retrieve(
        query="how to set up rate limiting?",
        agent=my_writer_agent,        # used to generate variants
        retriever=my_vector_retriever, # the actual retriever
        n_variants=3,
        k=5,
    )

    # HyDE: 1 query → 1 hypothetical answer → embed → retrieve
    results = await hyde_retrieve(
        query="explain TLS handshake",
        agent=my_agent,
        embedder=my_embed_fn,
        vector_store=my_vstore,
        k=5,
    )

    # RRF: combine results from N retrievers
    fused = rrf_fuse([
        bm25_results,
        vector_results,
        keyword_results,
    ], k=10)
"""

from __future__ import annotations
import logging
from typing import Awaitable, Callable

log = logging.getLogger("largestack.retrievers")


# -------------------- Multi-Query Retrieval --------------------

MULTI_QUERY_PROMPT = """Generate {n} alternative phrasings of this query \
that might match relevant documents indexed under different wording.

Original query: {query}

Output ONLY the alternative queries, one per line, no numbering, no \
explanations. Each line is a complete query."""


async def multi_query_retrieve(
    query: str,
    agent,
    retriever: Callable[[str, int], Awaitable[list[dict]]],
    n_variants: int = 3,
    k: int = 5,
    include_original: bool = True,
) -> list[dict]:
    """Multi-query retrieval: rewrite → retrieve each → fuse via RRF.

    Args:
        query: original user query.
        agent: an Agent (or anything with ``run(task) -> AgentResult``)
            used to generate alternative phrasings.
        retriever: async callable ``(query, k) -> list[dict]`` returning
            docs with at least ``id`` field. LARGESTACK vector stores
            implement this via ``store.query()``.
        n_variants: number of alternative phrasings (typical: 3-5).
        k: results per query and final result count.
        include_original: also retrieve with the original query.

    Returns:
        list of unique docs ranked by RRF, capped at ``k``.
    """
    if n_variants < 1:
        raise ValueError("n_variants must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")

    # 1. Generate variants
    prompt = MULTI_QUERY_PROMPT.format(n=n_variants, query=query)
    try:
        result = await agent.run(prompt, max_turns=1)
        text = getattr(result, "content", "") or ""
    except Exception as e:
        log.warning(f"multi-query: variant generation failed: {e}")
        text = ""

    variants = [
        line.strip().lstrip("0123456789.- ").strip() for line in text.splitlines() if line.strip()
    ]
    variants = [v for v in variants if v and v != query][:n_variants]

    # 2. Retrieve for each query
    queries_to_run = [query] + variants if include_original else variants
    if not queries_to_run:
        return []

    all_results: list[list[dict]] = []
    for q in queries_to_run:
        try:
            res = await retriever(q, k)
            all_results.append(res or [])
        except Exception as e:
            log.warning(f"multi-query: retriever failed for {q!r}: {e}")
            all_results.append([])

    # 3. Fuse via RRF
    fused = rrf_fuse(all_results, k=k)
    return fused


# -------------------- HyDE Retrieval --------------------

HYDE_PROMPT = """Write a concise hypothetical answer to this question — \
what a relevant document would say. Don't worry about being right; this \
is for retrieval. Be specific and factual-sounding.

Question: {query}

Hypothetical answer:"""


async def hyde_retrieve(
    query: str,
    agent,
    embedder: Callable[[str], Awaitable[list[float]]],
    vector_store,
    k: int = 5,
    filter: dict | None = None,
) -> list[dict]:
    """HyDE retrieval: LLM-generated hypothetical answer → embed → search.

    Args:
        query: original user query.
        agent: Agent used to generate the hypothetical answer.
        embedder: async callable ``(text) -> list[float]`` producing the
            embedding for the hypothetical answer. Use the SAME embedder
            that was used to index the corpus.
        vector_store: anything with ``query(vector, top_k, filter)``
            returning ``list[dict]``. LARGESTACK VectorStore implements this.
        k: number of results to return.
        filter: optional metadata filter passed through to the store.

    Returns:
        List of result dicts from the vector store.
    """
    if k < 1:
        raise ValueError("k must be >= 1")

    # 1. Hypothetical answer
    try:
        result = await agent.run(HYDE_PROMPT.format(query=query), max_turns=1)
        hypo = getattr(result, "content", "") or ""
    except Exception as e:
        log.warning(f"HyDE: hypothetical answer failed: {e}; falling back to query")
        hypo = ""

    # If the LLM failed, fall back to embedding the query directly
    text_to_embed = hypo.strip() if hypo.strip() else query

    # 2. Embed
    try:
        vec = await embedder(text_to_embed)
    except Exception as e:
        log.warning(f"HyDE: embedding failed: {e}")
        return []

    if not vec:
        return []

    # 3. Search
    try:
        results = await vector_store.query(vec, top_k=k, filter=filter)
    except TypeError:
        # store.query may not accept filter kwarg
        results = await vector_store.query(vec, top_k=k)
    return results or []


# -------------------- Reciprocal Rank Fusion --------------------


def rrf_fuse(
    result_lists: list[list[dict]],
    k: int = 10,
    rrf_k: int = 60,
    id_field: str = "id",
) -> list[dict]:
    """Fuse multiple ranked result lists via Reciprocal Rank Fusion.

    For each document, compute RRF score = Σ over lists of 1 / (rrf_k + rank).
    The standard ``rrf_k`` from the original paper is 60.

    Args:
        result_lists: list of result lists. Each inner list is a ranked
            sequence of dicts where each has ``id_field`` (default "id").
        k: number of results to return.
        rrf_k: RRF smoothing constant. 60 is the canonical value.
        id_field: which field to use as the unique document identifier.

    Returns:
        merged list of dicts, sorted by RRF score, capped at ``k``.
        Each dict includes added ``rrf_score`` field.

    Notes:
        - Documents missing the id_field are dropped (logged at debug level).
        - Ties broken by which document appeared first in the lists.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    if rrf_k < 1:
        raise ValueError("rrf_k must be >= 1")

    scores: dict = {}  # id -> {score: float, doc: dict}

    for results in result_lists:
        if not results:
            continue
        for rank, doc in enumerate(results, start=1):
            if not isinstance(doc, dict):
                continue
            doc_id = doc.get(id_field)
            if doc_id is None:
                log.debug(f"rrf_fuse: dropping doc without {id_field!r}")
                continue
            inc = 1.0 / (rrf_k + rank)
            if doc_id in scores:
                scores[doc_id]["score"] += inc
            else:
                scores[doc_id] = {"score": inc, "doc": dict(doc)}

    ordered = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

    out = []
    for entry in ordered[:k]:
        d = entry["doc"]
        d["rrf_score"] = round(entry["score"], 6)
        out.append(d)
    return out


# -------------------- v0.8.0 New Retrievers --------------------

# ----- Sentence-Window -----


def sentence_window_expand(
    results: list[dict],
    *,
    text_field: str = "content",
    window_chars: int = 500,
    full_doc_field: str = "full_document",
) -> list[dict]:
    """Expand each result with surrounding context.

    Use after vector retrieval: vector search picks tight chunks for
    precision; this expansion adds surrounding context for the LLM to
    reason about. The original chunk text is preserved at ``content``;
    expanded version goes to ``windowed_content``.

    Args:
        results: list of dicts. Each may have ``full_document`` in
            metadata pointing to its source doc text. If absent, the
            original ``content`` is kept unchanged.
        text_field: field with the chunk text.
        window_chars: characters of context on each side.
        full_doc_field: metadata key holding the parent document text.

    Returns:
        New list of dicts (original mutated copy) with ``windowed_content``
        added. Always returns; never raises.
    """
    if window_chars < 0:
        raise ValueError("window_chars must be >= 0")
    out = []
    for r in results:
        if not isinstance(r, dict):
            continue
        chunk = r.get(text_field, "") or ""
        full = (r.get("metadata") or {}).get(full_doc_field, "")
        new = dict(r)
        if not full or not chunk:
            new["windowed_content"] = chunk
            out.append(new)
            continue
        idx = full.find(chunk)
        if idx < 0:
            new["windowed_content"] = chunk
        else:
            start = max(0, idx - window_chars)
            end = min(len(full), idx + len(chunk) + window_chars)
            new["windowed_content"] = full[start:end]
        out.append(new)
    return out


# ----- Parent Document Retriever -----


async def parent_document_retrieve(
    query: str,
    *,
    chunk_retriever,
    parent_lookup,
    k: int = 5,
    chunks_per_query: int = 20,
) -> list[dict]:
    """Parent-document retrieval: search small chunks → return full parents.

    Indexes use small chunks (better precision) but the LLM gets the
    full parent document (better context).

    Args:
        query: search query.
        chunk_retriever: async ``(query, k) -> list[dict]`` searching chunks.
            Each chunk dict must have ``metadata.parent_id``.
        parent_lookup: async ``(parent_id) -> dict`` returning the parent
            doc with ``content`` and ``metadata``.
        k: number of unique parents to return.
        chunks_per_query: how many chunks to retrieve before deduplicating
            to parents.

    Returns:
        List of parent docs in retrieval order, deduplicated.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    chunks = await chunk_retriever(query, chunks_per_query)
    seen_parents: set = set()
    parents: list[dict] = []
    for c in chunks or []:
        pid = (c.get("metadata") or {}).get("parent_id")
        if pid is None or pid in seen_parents:
            continue
        seen_parents.add(pid)
        try:
            parent = await parent_lookup(pid)
        except Exception as e:
            log.debug(f"parent_lookup({pid}) failed: {e}")
            continue
        if parent:
            # Carry over the chunk's score
            parent["score"] = c.get("score", 0.0)
            parents.append(parent)
        if len(parents) >= k:
            break
    return parents


# ----- Auto-merging Retriever -----


async def auto_merging_retrieve(
    query: str,
    *,
    leaf_retriever,
    parent_lookup,
    k: int = 5,
    leaves_per_query: int = 20,
    merge_threshold: float = 0.5,
) -> list[dict]:
    """Auto-merging retrieval: if many leaf chunks share a parent, return parent.

    Documents are pre-chunked hierarchically: parent chunk → leaf chunks.
    Vector search runs on leaves (better matching). If ``merge_threshold``
    fraction of a parent's leaves are retrieved, the parent is returned
    instead — better context for the LLM.

    Args:
        query: search query.
        leaf_retriever: ``(query, k) -> list[dict]`` searching leaf chunks.
            Leaves must have ``metadata.parent_id`` and
            ``metadata.parent_total_leaves`` (count of siblings).
        parent_lookup: ``(parent_id) -> dict`` to fetch parent doc.
        k: number of results to return.
        leaves_per_query: how many leaves to retrieve.
        merge_threshold: fraction (0-1) of a parent's leaves needed to
            trigger the merge. Default 0.5.

    Returns:
        Mixed list of leaves and merged parents.
    """
    if not (0 < merge_threshold <= 1):
        raise ValueError("merge_threshold must be in (0, 1]")
    if k < 1:
        raise ValueError("k must be >= 1")

    leaves = await leaf_retriever(query, leaves_per_query) or []

    # Group leaves by parent_id
    by_parent: dict = {}
    for leaf in leaves:
        meta = leaf.get("metadata") or {}
        pid = meta.get("parent_id")
        if pid is not None:
            by_parent.setdefault(pid, []).append(leaf)

    # Decide which parents to merge
    merged_parents: dict = {}
    leaves_consumed: set = set()
    for pid, group in by_parent.items():
        total = (group[0].get("metadata") or {}).get("parent_total_leaves", len(group))
        if total > 0 and len(group) / total >= merge_threshold:
            try:
                parent = await parent_lookup(pid)
            except Exception as e:
                log.debug(f"parent_lookup({pid}) failed: {e}")
                continue
            if parent:
                # Average score of grouped leaves
                avg_score = sum(l.get("score", 0.0) for l in group) / max(1, len(group))
                parent["score"] = avg_score
                parent.setdefault("metadata", {})["merged_from_n_leaves"] = len(group)
                merged_parents[pid] = parent
                for leaf in group:
                    leaves_consumed.add(id(leaf))

    # Build final result: merged parents + non-merged leaves, sorted by score
    out_items: list[dict] = list(merged_parents.values())
    for leaf in leaves:
        if id(leaf) not in leaves_consumed:
            out_items.append(leaf)
    out_items.sort(key=lambda d: d.get("score", 0.0), reverse=True)
    return out_items[:k]


# ----- Recursive Retriever -----


async def recursive_retrieve(
    query: str,
    *,
    initial_retriever,
    follow_lookup,
    k: int = 5,
    depth: int = 2,
    follow_field: str = "references",
) -> list[dict]:
    """Recursive retrieval: retrieve, follow doc references, retrieve more.

    Useful for structured document graphs (e.g. Wikipedia-style with
    inter-doc references) where the answer might be in a doc linked
    from a high-scoring doc.

    Args:
        query: search query.
        initial_retriever: ``(query, k) -> list[dict]`` for the first pass.
        follow_lookup: ``(doc_id) -> dict`` to fetch a referenced document.
        k: final number of unique documents to return.
        depth: recursion depth (1 = no recursion, 2 = follow once, etc.).
        follow_field: metadata key listing related/referenced doc IDs.

    Returns:
        Deduplicated list of documents up to k.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    if k < 1:
        raise ValueError("k must be >= 1")

    seen_ids: set = set()
    out: list[dict] = []

    initial = await initial_retriever(query, k * 2) or []
    queue: list = [(d, 1) for d in initial]
    while queue:
        doc, current_depth = queue.pop(0)
        doc_id = doc.get("id")
        if doc_id in seen_ids:
            continue
        if doc_id is not None:
            seen_ids.add(doc_id)
        out.append(doc)
        if len(out) >= k:
            break
        if current_depth < depth:
            refs = (doc.get("metadata") or {}).get(follow_field) or []
            for ref_id in refs:
                if ref_id in seen_ids:
                    continue
                try:
                    ref_doc = await follow_lookup(ref_id)
                except Exception as e:
                    log.debug(f"follow_lookup({ref_id}) failed: {e}")
                    continue
                if ref_doc:
                    queue.append((ref_doc, current_depth + 1))
    return out[:k]


# ----- Time-Weighted Retriever -----

import time as _time


def time_weighted_rerank(
    results: list[dict],
    *,
    decay_rate: float = 0.01,
    timestamp_field: str = "timestamp",
    now: float | None = None,
    score_field: str = "score",
) -> list[dict]:
    """Re-rank results boosting recent documents.

    Standard formula: ``new_score = original_score * (1 - decay_rate)^age_hours``.
    Documents without timestamps get the original score unchanged.

    Args:
        results: list of dicts with ``score`` and metadata containing
            ``timestamp`` (Unix epoch seconds).
        decay_rate: per-hour decay (0.01 = 1% per hour).
        timestamp_field: metadata key for the timestamp.
        now: override current time (for testing).
        score_field: which score field to update.

    Returns:
        New list, re-sorted by ``time_weighted_score``.
    """
    if not (0 <= decay_rate < 1):
        raise ValueError("decay_rate must be in [0, 1)")
    current = now if now is not None else _time.time()
    rescored = []
    for r in results:
        if not isinstance(r, dict):
            continue
        new = dict(r)
        original_score = float(new.get(score_field, 0.0))
        ts = (new.get("metadata") or {}).get(timestamp_field)
        if ts is None:
            new["time_weighted_score"] = original_score
        else:
            try:
                age_hours = max(0.0, (current - float(ts)) / 3600.0)
                multiplier = max(0.0, (1 - decay_rate) ** age_hours)
                new["time_weighted_score"] = round(original_score * multiplier, 6)
            except (TypeError, ValueError):
                new["time_weighted_score"] = original_score
        rescored.append(new)
    rescored.sort(key=lambda d: d.get("time_weighted_score", 0.0), reverse=True)
    return rescored


# ----- Document Summary Retriever -----


async def document_summary_retrieve(
    query: str,
    *,
    summary_retriever,
    full_doc_lookup,
    k: int = 5,
) -> list[dict]:
    """Search over per-document summaries; return matching full docs.

    Pattern: pre-compute one summary embedding per document. Search the
    summary index (much smaller than chunk index). For each summary hit,
    return the FULL document so the LLM has complete context.

    Args:
        query: search query.
        summary_retriever: ``(query, k) -> list[dict]`` searching summaries.
            Each summary dict must have ``metadata.doc_id``.
        full_doc_lookup: ``(doc_id) -> dict`` returning the full document.
        k: number of full docs to return.

    Returns:
        List of full documents ordered by summary match score.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    summaries = await summary_retriever(query, k) or []
    docs: list[dict] = []
    for s in summaries:
        doc_id = (s.get("metadata") or {}).get("doc_id")
        if doc_id is None:
            continue
        try:
            full = await full_doc_lookup(doc_id)
        except Exception as e:
            log.debug(f"full_doc_lookup({doc_id}) failed: {e}")
            continue
        if full:
            full["score"] = s.get("score", 0.0)
            docs.append(full)
        if len(docs) >= k:
            break
    return docs


# -------------------- v0.9.0: 3 more retrievers --------------------


async def compression_retrieve(
    query: str,
    *,
    retriever: Callable,
    compressor_agent,
    k: int = 5,
    max_chars_per_doc: int = 500,
) -> list[dict]:
    """Compression retriever — uses an LLM to extract only relevant
    sentences from each retrieved document, dramatically reducing context
    size while preserving relevance.

    For each doc returned by ``retriever``, the compressor agent is
    asked to extract only sentences relevant to the query. If nothing
    is relevant, the doc is dropped.

    Args:
        query: user's query.
        retriever: async callable(query, k=N) -> list of docs.
        compressor_agent: LARGESTACK Agent used to extract relevant sentences.
        k: top-k from base retriever.
        max_chars_per_doc: cap on compressed content per doc.

    Returns:
        Compressed doc list. Each doc has a ``compressed_content`` field
        in addition to original ``content``.
    """
    base_docs = await retriever(query, k=k)
    if not base_docs:
        return []

    out = []
    for doc in base_docs:
        content = doc.get("content", "")
        if not content:
            continue
        prompt = (
            f"Extract ONLY the sentences from the document below that are "
            f"directly relevant to answering this query. If nothing in the "
            f"document is relevant, respond with 'NONE'.\n\n"
            f"Query: {query}\n\n"
            f"Document:\n{content[:5000]}\n\n"
            f"Relevant sentences:"
        )
        try:
            resp = await compressor_agent.run(prompt)
            compressed = (getattr(resp, "content", "") or "").strip()
        except Exception as e:
            log.debug(f"compression failed for doc: {e}")
            compressed = content[:max_chars_per_doc]

        if compressed.upper().strip() in {"NONE", "NONE.", ""}:
            continue
        if len(compressed) > max_chars_per_doc:
            compressed = compressed[:max_chars_per_doc] + "...[truncated]"

        result = dict(doc)
        result["compressed_content"] = compressed
        out.append(result)

    return out


async def self_query_retrieve(
    query: str,
    *,
    retriever: Callable,
    parser_agent,
    metadata_fields: dict[str, str],
    k: int = 5,
) -> list[dict]:
    """Self-query retriever — LLM extracts metadata filters from a
    natural-language query and applies them alongside semantic search.

    For example, "Find blog posts about Rust from 2023" becomes:
    - semantic query: "blog posts about Rust"
    - metadata filter: ``{"year": 2023, "type": "blog"}``

    Args:
        query: user's natural-language query.
        retriever: async callable(query, k=N, filter=dict) -> list[dict].
        parser_agent: LARGESTACK Agent used to parse query → (text, filters).
        metadata_fields: dict of {field_name: description} the agent can use.
            E.g., ``{"year": "publication year (int)", "category": "doc category"}``.
        k: top-k from retriever.
    """
    field_descriptions = "\n".join(f"- {name}: {desc}" for name, desc in metadata_fields.items())
    prompt = (
        f"Parse this query into (1) the semantic search text and "
        f"(2) any metadata filters. Available filter fields:\n"
        f"{field_descriptions}\n\n"
        f"Query: {query}\n\n"
        f"Respond with JSON only:\n"
        f'{{"search_text": "...", "filters": {{...}}}}'
    )
    try:
        resp = await parser_agent.run(prompt)
        content = (getattr(resp, "content", "") or "").strip()
        # Strip code fences
        for f in ["```json", "```"]:
            content = content.replace(f, "")
        content = content.strip()
        import json as _json

        parsed = _json.loads(content)
        search_text = parsed.get("search_text", query)
        filters = parsed.get("filters", {}) or {}
    except Exception as e:
        log.debug(f"self-query parse failed: {e}; falling back to plain query")
        search_text = query
        filters = {}

    # Validate filter keys against allowed fields
    filters = {k: v for k, v in filters.items() if k in metadata_fields}

    try:
        return await retriever(search_text, k=k, filter=filters)
    except TypeError:
        # retriever doesn't accept filter; fall back to non-filtered
        return await retriever(search_text, k=k)


async def ensemble_v2_retrieve(
    query: str,
    *,
    retrievers: list[tuple[Callable, float]],
    k: int = 10,
    fusion: str = "rrf",
) -> list[dict]:
    """Ensemble retriever v2 — combine N retrievers with weights.

    More flexible than v0.7's RRF: per-retriever weights, choice of
    fusion algorithm.

    Args:
        query: user's query.
        retrievers: list of ``(retriever_fn, weight)`` tuples.
        k: how many to return.
        fusion: ``"rrf"`` (default), ``"weighted_score"``, or ``"max_score"``.

    Returns:
        Fused list of top-k docs.
    """
    import asyncio as _asyncio

    if not retrievers:
        return []

    # Run all retrievers in parallel
    async def _run_one(retriever, weight):
        try:
            docs = await retriever(query, k=k)
            return docs, weight
        except Exception as e:
            log.debug(f"retriever failed: {e}")
            return [], weight

    pairs = await _asyncio.gather(*[_run_one(r, w) for r, w in retrievers])

    if fusion == "rrf":
        # Weighted RRF: each rank counts as weight / (60 + rank)
        scores: dict[str, float] = {}
        doc_map: dict[str, dict] = {}
        for docs, weight in pairs:
            for rank, doc in enumerate(docs, start=1):
                doc_id = str(doc.get("id", id(doc)))
                scores[doc_id] = scores.get(doc_id, 0.0) + weight / (60 + rank)
                if doc_id not in doc_map:
                    doc_map[doc_id] = doc
    elif fusion == "weighted_score":
        scores = {}
        doc_map = {}
        for docs, weight in pairs:
            for doc in docs:
                doc_id = str(doc.get("id", id(doc)))
                s = doc.get("score", 0.0)
                scores[doc_id] = scores.get(doc_id, 0.0) + weight * float(s)
                if doc_id not in doc_map:
                    doc_map[doc_id] = doc
    elif fusion == "max_score":
        scores = {}
        doc_map = {}
        for docs, weight in pairs:
            for doc in docs:
                doc_id = str(doc.get("id", id(doc)))
                s = float(doc.get("score", 0.0)) * weight
                if s > scores.get(doc_id, -1e9):
                    scores[doc_id] = s
                    doc_map[doc_id] = doc
    else:
        raise ValueError(f"unknown fusion: {fusion}")

    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    out = []
    for doc_id in sorted_ids[:k]:
        d = dict(doc_map[doc_id])
        d["fusion_score"] = scores[doc_id]
        out.append(d)
    return out
