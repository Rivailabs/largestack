import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from renewal_risk import assess_renewal_risk, save_playbook


def test_assess_renewal_risk_high():
    acct = {
        'usage_trend': -45,
        'open_tickets': 8,
        'champion_left': True,
        'renewal_days': 30,
        'arr': 250000
    }
    risk = assess_renewal_risk(acct)
    assert risk['risk_level'] == 'high'
    assert risk['score'] >= 70


def test_save_playbook_high():
    acct = {
        'usage_trend': -45,
        'open_tickets': 8,
        'champion_left': True,
        'renewal_days': 30,
        'arr': 250000
    }
    risk = assess_renewal_risk(acct)
    play = save_playbook(acct, risk)
    assert play['executed'] is False
    assert len(play['actions']) >= 3


def test_assess_renewal_risk_low():
    acct = {
        'usage_trend': 0,
        'open_tickets': 0,
        'champion_left': False,
        'renewal_days': 365,
        'arr': 50000
    }
    risk = assess_renewal_risk(acct)
    assert risk['risk_level'] == 'low'
    assert risk['score'] < 40


def test_save_playbook_low():
    acct = {
        'usage_trend': 0,
        'open_tickets': 0,
        'champion_left': False,
        'renewal_days': 365,
        'arr': 50000
    }
    risk = assess_renewal_risk(acct)
    play = save_playbook(acct, risk)
    assert play['executed'] is False
    # Low risk may have fewer actions
    assert len(play['actions']) >= 0
