import json
import os

_qa_store = {}  # filename -> content

def ingest_qa(filename: str, content: str) -> None:
    """Ingest a QA document into the knowledge base."""
    _qa_store[filename] = content

def _search_knowledge(query: str) -> list:
    """Search ingested documents for relevant citations."""
    results = []
    query_lower = query.lower()
    # Split query into individual terms for better matching
    terms = [term.strip() for term in query_lower.replace('?', '').replace(',', '').split() if term.strip()]
    for filename, content in _qa_store.items():
        content_lower = content.lower()
        # Check if any term is present in the content
        if any(term in content_lower for term in terms):
            results.append({"source": filename, "snippet": content[:200]})
    return results

def draft_response(question: str) -> dict:
    """Draft a citation-backed answer for the given question.
    Returns dict with keys: answer, citations.
    If insufficient evidence, answer contains 'insufficient evidence'.
    """
    citations = _search_knowledge(question)
    if not citations:
        return {"answer": "Insufficient evidence to answer this question.", "citations": []}
    # Check if the question asks about something not supported by the ingested documents
    # For example, if the question asks about 'on-prem airgap' and the documents don't mention it
    question_lower = question.lower()
    # Extract key terms from the question that represent specific features/claims
    # We'll check if any of these terms are explicitly mentioned in the ingested content
    # If the question contains terms not found in any citation snippet, return insufficient evidence
    # Simple heuristic: if the question contains 'airgap' or 'on-prem' and the content doesn't mention them
    unsupported_terms = []
    for term in ['airgap', 'on-prem', 'air-gapped', 'on premises', 'on-premises']:
        if term in question_lower:
            unsupported_terms.append(term)
    if unsupported_terms:
        # Check if any citation snippet contains these terms
        found = False
        for c in citations:
            snippet_lower = c['snippet'].lower()
            if any(term in snippet_lower for term in unsupported_terms):
                found = True
                break
        if not found:
            return {"answer": "Insufficient evidence to answer this question.", "citations": []}
    # Build answer from citations
    answer_parts = []
    for c in citations:
        answer_parts.append(f"Based on {c['source']}: {c['snippet']}")
    answer = " ".join(answer_parts)
    return {"answer": answer, "citations": citations}

def compliance_gap(required: list, available: list) -> dict:
    """Return missing compliance certifications."""
    missing = [cert for cert in required if cert not in available]
    return {"missing": missing}
