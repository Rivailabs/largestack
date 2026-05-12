import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from incident_war_room import triage_incident, response_plan, approval_gate

def test_triage_severity_and_privacy():
    incident = {
        'data_exposed': True,
        'customers_affected': 1200,
        'service_down_minutes': 30,
        'source': 'prod alert'
    }
    triage = triage_incident(incident)
    assert triage['severity'] in {'sev1', 'critical'}, f"Unexpected severity: {triage['severity']}"
    assert triage['privacy_review_required'] is True

def test_response_plan_min_steps_and_time():
    incident = {
        'data_exposed': True,
        'customers_affected': 1200,
        'service_down_minutes': 30,
        'source': 'prod alert'
    }
    triage = triage_incident(incident)
    plan = response_plan(triage)
    assert len(plan['steps']) >= 3, f"Steps count: {len(plan['steps'])}"
    assert plan['minutes_to_first_update'] <= 60, f"Minutes: {plan['minutes_to_first_update']}"

def test_approval_gate_customer_notice():
    incident = {
        'data_exposed': True,
        'customers_affected': 1200,
        'service_down_minutes': 30,
        'source': 'prod alert'
    }
    triage = triage_incident(incident)
    gate = approval_gate('customer_notice', triage)
    assert gate['approval_required'] is True
    assert gate['executed'] is False

def test_approval_gate_other_action():
    triage = {'severity': 'sev3'}
    gate = approval_gate('internal_log', triage)
    assert gate['approval_required'] is False
    assert gate['executed'] is True
