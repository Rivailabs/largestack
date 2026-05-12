import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from support_copilot import add_article, answer_question, escalation_decision

def setup_function():
    # Clear in-memory articles before each test
    import support_copilot
    support_copilot._articles.clear()

def test_add_and_retrieve():
    add_article('sso.md', 'SAML SSO setup requires metadata upload and admin approval.')
    ans = answer_question('how setup saml sso metadata?')
    assert 'metadata' in ans['answer'].lower()
    assert 'sso.md' in ans['citations']

def test_insufficient_evidence():
    add_article('sso.md', 'SAML SSO setup requires metadata upload and admin approval.')
    ans = answer_question('billing tax id?')
    assert 'insufficient evidence' in ans['answer'].lower()

def test_escalation_security():
    esc = escalation_decision('delete all data now')
    assert esc['approval_required'] is True
    assert esc['reason']
    assert esc['executed'] is False

def test_escalation_payment():
    esc = escalation_decision('process payment now')
    assert esc['approval_required'] is True
    assert esc['reason']
    assert esc['executed'] is False

def test_escalation_safe():
    esc = escalation_decision('what is the weather?')
    assert esc['approval_required'] is False
    assert esc['executed'] is True
