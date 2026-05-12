import json
import os


def assess_renewal_risk(acct):
    """
    Assess renewal risk for a B2B account.
    Returns dict with score (0-100) and risk_level ('low','medium','high').
    """
    score = 0
    # Usage decline: -1% -> +1 point, up to max 40
    usage = acct.get('usage_trend', 0)
    if usage < 0:
        score += min(abs(usage), 40)
    # Open tickets: each ticket +3 points, max 30
    tickets = acct.get('open_tickets', 0)
    score += min(tickets * 3, 30)
    # Champion loss: +20 points
    if acct.get('champion_left', False):
        score += 20
    # Renewal days: if <= 60, add (60 - days) * 0.5, max 30
    days = acct.get('renewal_days', 365)
    if days <= 60:
        score += min((60 - days) * 0.5, 30)
    # Contract value: ARR > 200k adds 10 points
    arr = acct.get('arr', 0)
    if arr > 200000:
        score += 10
    # Cap at 100
    score = min(score, 100)
    if score >= 70:
        risk_level = 'high'
    elif score >= 40:
        risk_level = 'medium'
    else:
        risk_level = 'low'
    return {'score': score, 'risk_level': risk_level}


def save_playbook(acct, risk):
    """
    Generate a playbook of mitigation actions based on risk assessment.
    Returns dict with actions list, approval_required, and executed flag.
    """
    actions = []
    if acct.get('usage_trend', 0) < -20:
        actions.append('Schedule executive business review')
    if acct.get('open_tickets', 0) > 5:
        actions.append('Escalate support tickets to priority queue')
    if acct.get('champion_left', False):
        actions.append('Assign new executive sponsor')
    if acct.get('renewal_days', 365) <= 30:
        actions.append('Initiate renewal contract negotiation')
    if acct.get('arr', 0) > 200000:
        actions.append('Offer retention discount')
    # Ensure at least 3 actions for high risk
    if risk['risk_level'] == 'high' and len(actions) < 3:
        actions.append('Conduct customer health check')
    return {
        'actions': actions,
        'approval_required': True,
        'executed': False
    }
