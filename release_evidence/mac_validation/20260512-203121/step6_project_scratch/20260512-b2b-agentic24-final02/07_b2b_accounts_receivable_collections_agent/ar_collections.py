import json
from typing import List, Dict, Any

def prioritize_accounts(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rank overdue invoices by priority score.
    Score = days_past_due * 0.4 + amount_due * 0.3 + tier_bonus + dispute_penalty + risk_penalty
    """
    tier_bonus_map = {'strategic': 20, 'standard': 10, 'low': 5}
    risk_penalty_map = {'low': 0, 'medium': -10, 'high': -20}
    
    for acc in accounts:
        score = 0.0
        score += acc.get('days_past_due', 0) * 0.4
        score += acc.get('amount_due', 0) * 0.3
        tier = acc.get('tier', 'standard')
        score += tier_bonus_map.get(tier, 10)
        if acc.get('disputed', False):
            score -= 30
        risk = acc.get('risk', 'low')
        score += risk_penalty_map.get(risk, 0)
        acc['priority_score'] = round(score, 2)
    
    ranked = sorted(accounts, key=lambda x: x['priority_score'], reverse=True)
    return ranked

def draft_collection_plan(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    Draft a collection plan for a single account.
    Never sends messages; always requires approval.
    """
    plan = {
        'account': account['account'],
        'amount_due': account['amount_due'],
        'days_past_due': account['days_past_due'],
        'tier': account.get('tier', 'standard'),
        'disputed': account.get('disputed', False),
        'priority_score': account.get('priority_score', 0),
        'send_executed': False,
        'approval_required': True,
        'actions': []
    }
    
    if account['days_past_due'] > 60:
        plan['actions'].append('Escalate to supervisor')
    elif account['days_past_due'] > 30:
        plan['actions'].append('Send reminder email (pending approval)')
    else:
        plan['actions'].append('No immediate action')
    
    if account.get('disputed', False):
        plan['actions'].append('Flag for dispute resolution')
    
    return plan
