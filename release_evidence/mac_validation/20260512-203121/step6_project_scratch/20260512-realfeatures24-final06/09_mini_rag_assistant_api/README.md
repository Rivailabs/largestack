# Mini RAG Assistant API

A minimal Retrieval-Augmented Generation assistant that answers queries based on document overlap.

## Run

```bash
python -c "from rag_assistant import RAGAssistant; a = RAGAssistant(); a.add_document('test.md', 'Hello world.'); print(a.answer('hello world'))"
```

## Test

```bash
pytest tests/test_rag_assistant.py -v
```

## Usage

- `add_document(filename, content)`: Add a document to the store.
- `answer(query)`: Returns dict with 'answer' and 'citations'. Returns 'Insufficient evidence' if not enough token overlap.
