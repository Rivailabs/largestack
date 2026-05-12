import sys
sys.path.insert(0, '.')
from revops_pipeline import normalize_lead, route_account, build_sla_plan

def test_normalize_lead():
    lead = normalize_lead({'email':'Buyer@ACME.COM','company':'  Acme Inc. ','employees':1500,'source':'web','last_touch_days':5})
    assert lead['domain'] == 'acme.com'
    assert lead['company'] == 'Acme Inc.'

def test_route_account_enterprise():
    lead = {'employees': 1500, 'last_touch_days': 5}
    route = route_account(lead)
    assert route['queue'] == 'enterprise_ae'
    assert route['priority'] in {'high', 'urgent'}

def test_route_account_escalation():
    lead = {'employees': 1500, 'last_touch_days': 45}
    route = route_account(lead)
    assert route['queue'] == 'escalation'
    assert route['priority'] == 'urgent'

def test_build_sla_plan_escalate():
    sla = build_sla_plan({'last_touch_days': 10})
    assert sla['escalate'] is True
    assert sla['due_hours'] <= 24

def test_build_sla_plan_no_escalate():
    sla = build_sla_plan({'last_touch_days': 3})
    assert sla['escalate'] is False
    assert sla['due_hours'] == 48

def test_full_pipeline():
    lead = normalize_lead({'email':'Buyer@ACME.COM','company':'  Acme Inc. ','employees':1500,'source':'web','last_touch_days':5})
    route = route_account(lead)
    assert route['queue'] == 'enterprise_ae'
    assert route['priority'] in {'high', 'urgent'}
    sla = build_sla_plan({**lead, 'last_touch_days': 10})
    assert sla['escalate'] is True
    assert sla['due_hours'] <= 24
