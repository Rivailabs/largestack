"""Index documents into the vector store."""
import asyncio
import json
import os
from pathlib import Path

from largestack._loaders import load
from largestack._vectorstores import PgVectorStore
from largestack._integrations import openai_embed


async def main():
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/largestack")
    store = PgVectorStore(dsn=dsn, table="documents", dim=1536)

    docs = await load("./data/")
    print(f"Loaded {len(docs)} documents")

    for i, doc in enumerate(docs):
        emb_json = await openai_embed(doc["content"][:8000])
        emb = json.loads(emb_json).get("embedding", [])
        if emb:
            await store.upsert([{
                "id": f"doc_{i}",
                "vector": emb,
                "metadata": doc.get("metadata", {}),
            }])
    print(f"Indexed {len(docs)} documents")
    await store.close()


if __name__ == "__main__":
    asyncio.run(main())
