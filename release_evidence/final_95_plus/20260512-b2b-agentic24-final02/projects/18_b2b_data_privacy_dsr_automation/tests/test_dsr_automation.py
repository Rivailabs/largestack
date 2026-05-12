import sys
sys.path.insert(0, '.')
from dsr_automation import classify_request, fulfillment_plan, redaction_check

def test_classify_request():
    req = {'text': 'Please delete my profile and export invoices', 'identity_verified': False, 'email': 'person@example.com'}
    cls = classify_request(req)
    assert set(cls['request_types']) == {'delete', 'export'}, cls

def test_fulfillment_plan():
    req = {'text': 'Please delete my profile and export invoices', 'identity_verified': False, 'email': 'person@example.com'}
    cls = classify_request(req)
    plan = fulfillment_plan(req, cls)
    assert plan['approval_required'] is True and plan['executed'] is False, plan

def test_redaction_check():
    result = redaction_check('email person@example.com')
    assert 'person@example.com' not in result, 'PII not redacted'

def test_redaction_check_no_pii():
    result = redaction_check('no email here')
    assert result == 'no email here'
