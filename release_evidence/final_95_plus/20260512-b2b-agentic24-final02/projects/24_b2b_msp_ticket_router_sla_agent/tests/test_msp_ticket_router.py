import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from msp_ticket_router import route_ticket, sla_breach_risk, handoff_plan

def test_route_ticket():
    ticket = {'customer_tier': 'platinum', 'severity': 'p1', 'system': 'payments', 'region': 'apac', 'age_minutes': 50}
    route = route_ticket(ticket)
    assert route['queue'] == 'payments_p1'
    assert route['priority'] == 'urgent'

def test_sla_breach_risk():
    ticket = {'customer_tier': 'platinum', 'severity': 'p1', 'system': 'payments', 'region': 'apac', 'age_minutes': 50}
    risk = sla_breach_risk(ticket, sla_minutes=60)
    assert risk['breach_risk'] in {'high', 'critical'}
    assert risk['minutes_remaining'] == 10

def test_handoff_plan():
    ticket = {'customer_tier': 'platinum', 'severity': 'p1', 'system': 'payments', 'region': 'apac', 'age_minutes': 50}
    route = route_ticket(ticket)
    risk = sla_breach_risk(ticket, sla_minutes=60)
    handoff = handoff_plan(ticket, route, risk)
    assert handoff['notify_executed'] is False
    assert handoff['approval_required'] is True

def test_handoff_low_risk():
    ticket = {'customer_tier': 'standard', 'severity': 'p3', 'system': 'general', 'region': 'us', 'age_minutes': 5}
    route = route_ticket(ticket)
    risk = sla_breach_risk(ticket, sla_minutes=60)
    handoff = handoff_plan(ticket, route, risk)
    assert handoff['notify_executed'] is False
    assert handoff['approval_required'] is False
