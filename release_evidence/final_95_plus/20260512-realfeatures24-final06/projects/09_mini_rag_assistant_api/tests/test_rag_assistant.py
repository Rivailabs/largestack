import sys
sys.path.insert(0, '.')
from rag_assistant import _documents, add_document, answer

def setup_function():
    _documents.clear()

def test_duplicate_payments():
    add_document('refund_policy.md', 'Duplicate payments require approval before refund.')
    result = answer('duplicate payments require what?')
    assert result['answer'] == 'Duplicate payments require approval before refund.'
    assert 'refund_policy.md' in result['citations']

def test_insufficient_evidence():
    add_document('policy.md', 'Some other policy.')
    result = answer('equity refresh policy')
    assert result['answer'] == 'Insufficient evidence'
    assert result['citations'] == []

def test_clear_store():
    add_document('temp.md', 'Temporary content.')
    _documents.clear()
    assert len(_documents) == 0
