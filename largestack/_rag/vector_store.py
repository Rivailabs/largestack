"""Vector store abstraction — pgvector, in-memory, Qdrant."""

from __future__ import annotations

import json
import math
import re


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(name: str, *, label: str = "identifier") -> str:
    """Validate SQL identifiers that cannot be passed as query parameters."""
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValueError(f"invalid {label}: {name!r}")
    return name


def _validate_dim(dim: int) -> int:
    if not isinstance(dim, int) or dim <= 0 or dim > 100_000:
        raise ValueError(f"invalid vector dimension: {dim!r}")
    return dim


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


class InMemoryVectorStore:
    """In-memory vector store for development (no external DB needed)."""

    def __init__(self, dim: int = 128):
        self.dim = _validate_dim(dim)
        self._vectors: list[tuple[str, list[float], dict]] = []

    async def add(self, doc_id: str, vector: list[float], metadata: dict = None):
        self._vectors.append((doc_id, vector, metadata or {}))

    async def add_batch(self, items: list[tuple[str, list[float], dict]]):
        self._vectors.extend(items)

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[dict]:
        results = []
        for doc_id, vec, meta in self._vectors:
            score = self._cosine(query_vector, vec)
            if score >= threshold:
                results.append({"id": doc_id, "score": score, **meta})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, doc_id: str):
        self._vectors = [(i, v, m) for i, v, m in self._vectors if i != doc_id]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0

    def __len__(self):
        return len(self._vectors)


class PgVectorStore:
    """PostgreSQL + pgvector store (production). Requires asyncpg."""

    def __init__(
        self,
        connection_string: str,
        table: str = "largestack_vectors",
        dim: int = 1536,
    ):
        self.conn_str = connection_string
        self.table = _validate_identifier(table, label="table")
        self.index_name = _validate_identifier(f"idx_{self.table}_emb", label="index")
        self.dim = _validate_dim(dim)
        self._pool = None

    async def init(self):
        try:
            import asyncpg  # noqa: F401

            self._pool = await asyncpg.create_pool(self.conn_str)
            await self._pool.execute(
                f"""  # nosec B608
                CREATE TABLE IF NOT EXISTS {self.table} (
                    id TEXT PRIMARY KEY,
                    embedding vector({self.dim}),
                    content TEXT,
                    metadata JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
                """  # nosec B608
            )
            await self._pool.execute(
                f"""  # nosec B608
                CREATE INDEX IF NOT EXISTS {self.index_name}
                ON {self.table} USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 128)
                """  # nosec B608
            )
        except ImportError as e:
            raise ImportError("asyncpg required: pip install asyncpg") from e

    async def add(self, doc_id: str, vector: list[float], metadata: dict = None):
        sql = (
            f"INSERT INTO {self.table} (id, embedding, metadata) "  # nosec B608
            f"VALUES ($1, $2, $3) "
            f"ON CONFLICT (id) DO UPDATE SET embedding = $2"
        )
        await self._pool.execute(
            sql,
            doc_id,
            _vector_literal(vector),
            json.dumps(metadata or {}),
        )

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[dict]:
        sql = (
            f"SELECT id, metadata, 1 - (embedding <=> $1) as score "  # nosec B608
            f"FROM {self.table} "
            f"ORDER BY embedding <=> $1 "
            f"LIMIT $2"
        )
        rows = await self._pool.fetch(sql, _vector_literal(query_vector), top_k)
        return [
            {
                "id": r["id"],
                "score": float(r["score"]),
                **(json.loads(r["metadata"]) if r["metadata"] else {}),
            }
            for r in rows
            if float(r["score"]) >= threshold
        ]
