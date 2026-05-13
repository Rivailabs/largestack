import pytest
from esign_workflow import create_envelope, add_signer, send_decision, audit_trail

# Clear global state before each test
@pytest.fixture(autouse=True)
def clear_state():
    import esign_workflow
    esign_workflow._envelopes.clear()
    esign_workflow._audit_trail.clear()

def test_create_envelope():
    e = create_envelope('contract.pdf')
    assert 'id' in e
    assert e['document'] == 'contract.pdf'
    assert e['status'] == 'draft'

def test_add_signer():
    e = create_envelope('contract.pdf')
    signer = add_signer(e['id'], 'a@example.com')
    assert signer['email'] == 'a@example.com'
    assert signer['signed'] is False

def test_send_decision_returns_executed_false():
    e = create_envelope('contract.pdf')
    add_signer(e['id'], 'a@example.com')
    result = send_decision(e['id'])
    assert result['executed'] is False

def test_audit_trail_exists():
    e = create_envelope('contract.pdf')
    add_signer(e['id'], 'a@example.com')
    send_decision(e['id'])
    trail = audit_trail(e['id'])
    assert len(trail) >= 3
    # Check that send_attempt entry mentions approval required
    send_entries = [entry for entry in trail if entry['action'] == 'send_attempt']
    assert len(send_entries) == 1
    assert 'Approval is required' in send_entries[0]['details']

def test_full_workflow():
    e = create_envelope('contract.pdf')
    add_signer(e['id'], 'a@example.com')
    assert send_decision(e['id'])['executed'] is False
    assert audit_trail(e['id'])
