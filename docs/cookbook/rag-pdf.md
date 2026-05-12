# RAG with PDFs

```python
from largestack import create_rag, Agent
rag = create_rag(documents=["doc1.pdf", "doc2.pdf"])
agent = Agent(tools=[rag.as_tool()])
```
