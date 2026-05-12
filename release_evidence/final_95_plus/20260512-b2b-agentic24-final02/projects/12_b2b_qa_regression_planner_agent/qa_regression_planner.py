import json
import os

def load_policy():
    policy_path = os.path.join(os.path.dirname(__file__), 'policies', 'risk_policy.json')
    with open(policy_path) as f:
        return json.load(f)

def build_test_plan(changes, incidents):
    policy = load_policy()
    areas = set()
    for change in changes:
        area = change.split('/')[0]
        areas.add(area)
    for inc in incidents:
        areas.add(inc['area'])
    max_severity = 'low'
    for inc in incidents:
        sev = inc.get('severity', 'low')
        if sev == 'critical':
            max_severity = 'critical'
        elif sev == 'high' and max_severity != 'critical':
            max_severity = 'high'
        elif sev == 'medium' and max_severity not in ('critical','high'):
            max_severity = 'medium'
    priority = max_severity
    owners = {}
    for area in areas:
        owners[area] = policy.get('default_owner', 'qa-team')
    plan = {
        'areas': list(areas),
        'priority': priority,
        'smoke_tests': [],
        'regression_tests': [],
        'owners': owners
    }
    for area in areas:
        if priority in ('high','critical'):
            plan['smoke_tests'].append(f'{area}_smoke')
        plan['regression_tests'].append(f'{area}_regression')
    return plan

def risk_matrix(plan):
    policy = load_policy()
    matrix = {}
    for area in plan['areas']:
        sev = plan['priority']
        risk = policy.get('risk_mapping', {}).get(sev, 'medium')
        matrix[area] = {'risk': risk, 'owner': plan['owners'].get(area, 'qa-team')}
    return matrix
