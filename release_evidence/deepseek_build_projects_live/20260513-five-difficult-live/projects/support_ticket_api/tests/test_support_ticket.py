import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from support_ticket import handle_ticket

def test_duplicate_payment_refund():
    result = handle_ticket('I need a payment and refund')
    assert result['category'] == 'refund'
    assert result['approval_required'] == True

def test_refund_requires_approval():
    result = handle_ticket('I want a refund')
    assert result['category'] == 'refund'
    assert result['approval_required'] == True

def test_payment_requires_approval():
    result = handle_ticket('I want to make a payment')
    assert result['category'] == 'payment'
    assert result['approval_required'] == True

def test_login_reset_mentions_identity_verification():
    result = handle_ticket('I need to reset my login')
    assert result['category'] == 'login_reset'
    assert 'identity' in result['response'].lower() or 'verify' in result['response'].lower()

def test_general_no_approval():
    result = handle_ticket('I have a question')
    assert result['category'] == 'general'
    assert result['approval_required'] == False

def test_mixed_case():
    result = handle_ticket('Payment and Refund')
    assert result['category'] == 'refund'
    assert result['approval_required'] == True

def test_whitespace_handling():
    result = handle_ticket('  login reset  ')
    assert result['category'] == 'login_reset'
    assert 'identity' in result['response'].lower()
