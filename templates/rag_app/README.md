# RAG Application

LARGESTACK template for retrieval-augmented generation.

## Setup
```bash
pip install largestack[postgres]
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg16
export DATABASE_URL="postgresql://postgres:postgres@localhost/postgres"
export LARGESTACK_OPENAI_API_KEY="sk-..."
```

## Index documents
```bash
mkdir -p data && cp /path/to/your/*.md data/
python ingest.py
```

## Query
```bash
largestack run agent.yaml --task "What does the documentation say about X?"
```
