import pytest
from rfp_response import ingest_qa, draft_response, compliance_gap

def setup_function():
    # Clear global state before each test
    import rfp_response
    rfp_response._qa_store.clear()

def test_ingest_and_draft():
    ingest_qa('security.md', 'We support SSO, audit logs, and data export. SOC2 report available under NDA.')
    resp = draft_response('Do you support audit logs and SSO?')
    assert 'audit logs' in resp['answer'].lower()
    assert resp['citations']

def test_insufficient_evidence():
    ingest_qa('security.md', 'We support SSO, audit logs, and data export. SOC2 report available under NDA.')
    missing = draft_response('Do you support on-prem airgap?')
    assert 'insufficient evidence' in missing['answer'].lower()

def test_compliance_gap():
    gap = compliance_gap(['SOC2', 'HIPAA'], available=['SOC2'])
    assert gap['missing'] == ['HIPAA']
