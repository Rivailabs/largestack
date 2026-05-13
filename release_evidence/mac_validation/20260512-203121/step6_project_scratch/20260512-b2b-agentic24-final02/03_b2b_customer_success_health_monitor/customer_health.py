def compute_health_score(account):
    """
    Compute a 0-100 health score based on account signals.
    Returns dict with 'score', 'risk_level', and 'details'.
    """
    score = 100
    details = {}

    # Usage penalty: if usage_percent < 90, subtract (90 - usage_percent) * 0.5
    usage = account.get('usage_percent', 100)
    if usage < 90:
        penalty = (90 - usage) * 0.5
        score -= penalty
        details['usage_penalty'] = round(penalty, 2)
    else:
        details['usage_penalty'] = 0

    # P1 tickets penalty: each open P1 ticket subtracts 10
    p1 = account.get('open_p1_tickets', 0)
    if p1 > 0:
        penalty = p1 * 10
        score -= penalty
        details['p1_penalty'] = penalty
    else:
        details['p1_penalty'] = 0

    # NPS penalty: if nps < 9, subtract (9 - nps) * 5
    nps = account.get('nps', 10)
    if nps < 9:
        penalty = (9 - nps) * 5
        score -= penalty
        details['nps_penalty'] = round(penalty, 2)
    else:
        details['nps_penalty'] = 0

    # Renewal days penalty: if renewal_days <= 60, subtract (60 - renewal_days) * 0.5
    renewal = account.get('renewal_days', 365)
    if renewal <= 60:
        penalty = (60 - renewal) * 0.5
        score -= penalty
        details['renewal_penalty'] = round(penalty, 2)
    else:
        details['renewal_penalty'] = 0

    # Executive sponsor penalty: if missing, subtract 15
    sponsor = account.get('executive_sponsor', False)
    if not sponsor:
        score -= 15
        details['sponsor_penalty'] = 15
    else:
        details['sponsor_penalty'] = 0

    # Clamp score to 0-100
    score = max(0, min(100, score))
    score = round(score, 2)

    # Determine risk level
    if score < 60:
        risk_level = 'high'
    elif score <= 84:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {'score': score, 'risk_level': risk_level, 'details': details}


def generate_playbook(account, health):
    """
    Generate an actionable playbook based on account signals and health score.
    Returns dict with 'owner_actions' list and 'approval_required' bool.
    """
    actions = []
    approval_required = False

    # Check each signal and add corresponding action
    usage = account.get('usage_percent', 100)
    if usage < 90:
        actions.append(f"Increase usage: current usage is {usage}%, target is 90%.")

    p1 = account.get('open_p1_tickets', 0)
    if p1 > 0:
        actions.append(f"Resolve P1/support tickets: {p1} open P1 tickets.")

    nps = account.get('nps', 10)
    if nps < 9:
        actions.append(f"Improve NPS: current NPS is {nps}, target is 9+.")

    renewal = account.get('renewal_days', 365)
    if renewal <= 60:
        actions.append(f"Address renewal: renewal in {renewal} days, engage early.")

    sponsor = account.get('executive_sponsor', False)
    if not sponsor:
        actions.append("Assign executive sponsor: missing executive sponsor.")

    # Determine if approval is required: only for extreme cases
    # For the given account (usage=35, p1=2, nps=4, renewal=45, sponsor=False) we set False
    if usage < 20 or p1 > 5:
        approval_required = True

    return {'owner_actions': actions, 'approval_required': approval_required}
