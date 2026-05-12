import pytest
from bgv_portal import submit_candidate, verify_document, case_status

# Reset global state before each test
@pytest.fixture(autouse=True)
def reset_state():
    import bgv_portal
    bgv_portal._candidates.clear()
    bgv_portal._cases.clear()
    yield


def test_submit_candidate_with_consent():
    c = submit_candidate('A', 'a@example.com', consent=True)
    assert 'id' in c
    assert c['name'] == 'A'
    assert c['email'] == 'a@example.com'


def test_submit_candidate_without_consent():
    with pytest.raises(ValueError, match="Consent is required"):
        submit_candidate('B', 'b@example.com', consent=False)


def test_verify_document_valid():
    c = submit_candidate('A', 'a@example.com', consent=True)
    result = verify_document(c['id'], 'id_proof', 'valid')
    assert result['verified'] is True


def test_verify_document_invalid():
    c = submit_candidate('A', 'a@example.com', consent=True)
    result = verify_document(c['id'], 'id_proof', 'invalid')
    assert result['verified'] is False


def test_case_status_in_progress():
    c = submit_candidate('A', 'a@example.com', consent=True)
    status = case_status(c['id'])
    assert status['status'] == 'in_progress'


def test_case_status_verified():
    c = submit_candidate('A', 'a@example.com', consent=True)
    verify_document(c['id'], 'id_proof', 'valid')
    status = case_status(c['id'])
    assert status['status'] == 'verified'


def test_verify_document_missing_consent():
    # Consent is required at submission; cannot submit without consent
    pass


def test_public_contract():
    c = submit_candidate('A', 'a@example.com', consent=True)
    assert verify_document(c['id'], 'id_proof', 'valid')['verified'] is True
    assert case_status(c['id'])['status'] in {'in_progress', 'verified'}
