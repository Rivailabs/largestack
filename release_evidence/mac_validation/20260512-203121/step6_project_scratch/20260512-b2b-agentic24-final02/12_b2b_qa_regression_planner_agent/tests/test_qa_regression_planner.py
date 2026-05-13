import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from qa_regression_planner import build_test_plan, risk_matrix

def test_build_test_plan():
    changes = ['billing/payments.py', 'auth/sso.py']
    incidents = [{'area': 'billing', 'severity': 'high'}]
    plan = build_test_plan(changes, incidents)
    assert 'billing' in plan['areas']
    assert plan['priority'] == 'high'
    assert 'auth' in plan['areas']

def test_risk_matrix():
    changes = ['billing/payments.py', 'auth/sso.py']
    incidents = [{'area': 'billing', 'severity': 'high'}]
    plan = build_test_plan(changes, incidents)
    matrix = risk_matrix(plan)
    assert matrix['billing']['risk'] in {'high', 'critical'}

def test_public_contract():
    changes = ['billing/payments.py', 'auth/sso.py']
    incidents = [{'area': 'billing', 'severity': 'high'}]
    plan = build_test_plan(changes, incidents)
    assert 'billing' in plan['areas'] and plan['priority'] == 'high', plan
    matrix = risk_matrix(plan)
    assert matrix['billing']['risk'] in {'high', 'critical'}, matrix
