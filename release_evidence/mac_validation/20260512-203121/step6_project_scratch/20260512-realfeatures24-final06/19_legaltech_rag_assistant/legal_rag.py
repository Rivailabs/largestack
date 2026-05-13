import os
import re

_notes = {}  # source_name -> list of notes

def add_case_note(source_name: str, note: str) -> None:
    """Add a note to a case source."""
    if source_name not in _notes:
        _notes[source_name] = []
    _notes[source_name].append(note)

def answer_legal_query(query: str) -> dict:
    """Answer a legal query based on stored notes.
    Returns dict with 'answer' and 'citations'.
    """
    query_lower = query.lower()
    relevant = []
    for source, notes in _notes.items():
        for note in notes:
            if any(word in note.lower() for word in query_lower.split()):
                relevant.append((source, note))
    if not relevant:
        return {"answer": "No relevant information found.", "citations": []}
    # Combine notes into answer, cite sources
    answer_parts = []
    citations = []
    for source, note in relevant:
        answer_parts.append(note)
        if source not in citations:
            citations.append(source)
    answer = " ".join(answer_parts)
    return {"answer": answer, "citations": citations}
