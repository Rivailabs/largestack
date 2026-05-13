import re
from typing import Dict, List

_documents: Dict[str, str] = {}

def add_document(filename: str, content: str) -> None:
    _documents[filename] = content

def answer(query: str) -> Dict[str, object]:
    weak_words = {'what', 'why', 'how', 'does', 'the', 'a', 'an', 'is', 'are', 'before'}
    tokens = re.findall(r'\w+', query.lower())
    meaningful_tokens = [t for t in tokens if t not in weak_words]
    if len(meaningful_tokens) < 2:
        return {'answer': 'Insufficient evidence', 'citations': []}

    best_answer = None
    best_citations = []
    best_overlap = 0

    for filename, content in _documents.items():
        doc_tokens = set(re.findall(r'\w+', content.lower()))
        overlap = sum(1 for t in meaningful_tokens if t in doc_tokens)
        if overlap >= 2 and overlap > best_overlap:
            best_overlap = overlap
            best_answer = content
            best_citations = [filename]

    if best_answer is None:
        return {'answer': 'Insufficient evidence', 'citations': []}
    return {'answer': best_answer, 'citations': best_citations}
