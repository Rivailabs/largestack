import json
import os
from datetime import datetime, timedelta

def _load_policy(name):
    base = os.path.dirname(__file__)
    path = os.path.join(base, 'policies', name)
    with open(path) as f:
        return json.load(f)

def triage_incident(incident):
    rules = _load_policy('severity_rules.json')
    data_exposed = incident.get('data_exposed', False)
    customers = incident.get('customers_affected', 0)
    service_down = incident.get('service_down_minutes', 0)
    source = incident.get('source', '')

    sev = 'sev3'
    if data_exposed or customers >= rules['critical_customer_threshold'] or service_down >= rules['critical_downtime_minutes']:
        sev = 'critical'
    elif customers >= rules['sev1_customer_threshold'] or service_down >= rules['sev1_downtime_minutes']:
        sev = 'sev1'
    elif customers >= rules['sev2_customer_threshold'] or service_down >= rules['sev2_downtime_minutes']:
        sev = 'sev2'

    privacy_review = data_exposed or (sev in ('critical', 'sev1') and customers > 0)

    return {
        'severity': sev,
        'privacy_review_required': privacy_review,
        'data_exposed': data_exposed,
        'customers_affected': customers,
        'service_down_minutes': service_down,
        'source': source
    }

def response_plan(triage):
    sev = triage['severity']
    steps = []
    if sev in ('critical', 'sev1'):
        steps.append('Notify on-call engineer immediately')
        steps.append('Assess data exposure scope')
        steps.append('Engage privacy team if required')
        steps.append('Prepare customer notice draft')
        steps.append('Escalate to VP of Engineering')
        minutes_to_first = 15
    elif sev == 'sev2':
        steps.append('Notify team lead')
        steps.append('Investigate root cause')
        steps.append('Plan remediation')
        minutes_to_first = 30
    else:
        steps.append('Log incident for review')
        steps.append('Assign to next on-call')
        minutes_to_first = 60

    return {
        'steps': steps,
        'minutes_to_first_update': minutes_to_first,
        'severity': sev
    }

def approval_gate(action, triage):
    if action == 'customer_notice':
        return {
            'approval_required': True,
            'executed': False,
            'reason': 'External notice requires maker-checker approval'
        }
    return {
        'approval_required': False,
        'executed': True,
        'reason': 'No approval needed'
    }
