from __future__ import annotations

import json
import re
from pathlib import Path

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "rag_eval"
STOPWORDS = {"the", "a", "an", "and", "or", "to", "what", "which", "is", "are", "before", "happen"}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def load_docs() -> list[dict]:
    docs = []
    for path in sorted((FIXTURE_ROOT / "docs").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        tenant = None
        if "tenant: tenant-a" in text:
            tenant = "tenant-a"
        if "tenant: tenant-b" in text:
            tenant = "tenant-b"
        docs.append({"id": path.name, "content": text, "tenant_id": tenant})
    return docs


def load_questions() -> list[dict]:
    return [json.loads(line) for line in (FIXTURE_ROOT / "questions.jsonl").read_text(encoding="utf-8").splitlines() if line]


def retrieve(query: str, docs: list[dict] | None = None, *, top_k: int = 3, tenant_id: str | None = None, rerank: bool = False) -> list[dict]:
    q_tokens = tokenize(query)
    candidates = []
    for doc in docs or load_docs():
        if tenant_id and doc.get("tenant_id") not in {None, tenant_id}:
            continue
        d_tokens = tokenize(doc["content"])
        overlap = sum(1 for token in q_tokens if token in d_tokens)
        phrase_bonus = 3 if query.lower() in doc["content"].lower() else 0
        rare_bonus = sum(2 for token in q_tokens if token in {"rta", "bom", "dsd", "qp"} and token in d_tokens)
        score = overlap + phrase_bonus + rare_bonus
        if rerank and any(token in doc["content"].lower() for token in ["citation", "requires", "validation"]):
            score += 1
        candidates.append({**doc, "score": score})
    return sorted(candidates, key=lambda item: (-item["score"], item["id"]))[:top_k]


def recall_at_k(questions: list[dict], *, k: int) -> float:
    hits = 0
    for q in questions:
        hits += q["answer_doc"] in {doc["id"] for doc in retrieve(q["query"], top_k=k)}
    return hits / len(questions)


def mean_reciprocal_rank(questions: list[dict]) -> float:
    score = 0.0
    for q in questions:
        ranking = retrieve(q["query"], top_k=10)
        for idx, doc in enumerate(ranking, start=1):
            if doc["id"] == q["answer_doc"]:
                score += 1 / idx
                break
    return score / len(questions)


def answer_with_citation(query: str) -> str:
    top = retrieve(query, top_k=1)[0]
    m = re.search(r"Citation key: ([A-Z0-9-]+)", top["content"])
    citation = m.group(1) if m else top["id"]
    return f"Answer grounded in {top['id']} [{citation}]"


def build_large_corpus(size: int = 250) -> list[dict]:
    corpus = load_docs()
    for i in range(size):
        corpus.append({"id": f"noise-{i}.md", "content": f"generic operational note {i} without target vocabulary", "tenant_id": None})
    return corpus
