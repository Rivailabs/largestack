import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from support_ticket import handle_ticket

def test_refund_approval():
    r = handle_ticket('duplicate payment refund')
    assert r['approval_required'] is True
    assert r['category'] == 'refund'

def test_login_reset_identity():
    r = handle_ticket('login reset')
    assert 'identity' in r['response'].lower()

def test_payment_approval():
    r = handle_ticket('payment issue')
    assert r['approval_required'] is True
    assert r['category'] == 'refund'

def test_security_approval():
    r = handle_ticket('security breach')
    assert r['approval_required'] is True
    assert r['category'] == 'security'

def test_data_export_approval():
    r = handle_ticket('data export request')
    assert r['approval_required'] is True
    assert r['category'] == 'data_export'

def test_general_no_approval():
    r = handle_ticket('password reset')
    assert r['approval_required'] is False
    assert r['category'] == 'general'

def test_general_response():
    r = handle_ticket('hello')
    assert r['response'] == 'Request received.'
