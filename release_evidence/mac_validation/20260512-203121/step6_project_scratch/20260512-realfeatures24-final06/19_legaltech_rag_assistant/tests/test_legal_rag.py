import pytest
from legal_rag import add_case_note, answer_legal_query

def setup_function():
    # Clear global notes before each test
    import legal_rag
    legal_rag._notes.clear()

def test_add_and_query():
    add_case_note('contract.md', 'Termination requires 30 days written notice.')
    r = answer_legal_query('termination notice')
    assert '30' in r['answer']
    assert 'contract.md' in r['citations']
    assert 'guarantee' not in r['answer'].lower()

def test_no_notes():
    r = answer_legal_query('anything')
    assert r['answer'] == 'No relevant information found.'
    assert r['citations'] == []

def test_multiple_sources():
    add_case_note('source1.md', 'Notice period is 30 days.')
    add_case_note('source2.md', 'Termination requires written notice.')
    r = answer_legal_query('termination notice')
    assert '30' in r['answer']
    assert 'source1.md' in r['citations']
    assert 'source2.md' in r['citations']
