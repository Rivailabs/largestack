import json
import os

# Load routing rules from policy file
_policy_path = os.path.join(os.path.dirname(__file__), 'policies', 'routing_rules.json')
with open(_policy_path, 'r') as f:
    _rules = json.load(f)

def route_ticket(ticket):
    """Route ticket based on customer tier, severity, system, and region."""
    tier = ticket.get('customer_tier', 'standard')
    severity = ticket.get('severity', 'p3')
    system = ticket.get('system', 'general')
    region = ticket.get('region', 'us')
    
    # Determine queue from rules
    queue = _rules.get('queues', {}).get(severity, 'general')
    if system in _rules.get('system_overrides', {}):
        queue = _rules['system_overrides'][system]
    
    # Determine priority
    priority_map = _rules.get('priority_map', {})
    priority = priority_map.get(tier, 'normal')
    if severity in ('p1', 'p2'):
        priority = 'urgent'
    
    return {'queue': queue, 'priority': priority}

def sla_breach_risk(ticket, sla_minutes=60):
    """Calculate SLA breach risk based on ticket age and SLA threshold."""
    age = ticket.get('age_minutes', 0)
    remaining = sla_minutes - age
    if remaining <= 0:
        risk = 'critical'
    elif remaining <= 10:
        risk = 'high'
    elif remaining <= 30:
        risk = 'medium'
    else:
        risk = 'low'
    return {'breach_risk': risk, 'minutes_remaining': max(remaining, 0)}

def handoff_plan(ticket, route, risk):
    """Produce safe handoff plan without external notification."""
    # Risky actions require approval and are not executed
    if risk['breach_risk'] in ('high', 'critical'):
        return {
            'notify_executed': False,
            'approval_required': True,
            'reason': 'SLA breach risk requires approval before escalation'
        }
    return {
        'notify_executed': False,
        'approval_required': False,
        'reason': 'Routine handoff, no approval needed'
    }
