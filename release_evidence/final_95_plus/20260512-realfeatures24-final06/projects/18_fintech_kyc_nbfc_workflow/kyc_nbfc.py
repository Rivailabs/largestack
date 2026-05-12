def validate_kyc(case):
    """Validate KYC case. Returns dict with 'valid' bool and 'reason' string."""
    if not case.get('pan'):
        return {'valid': False, 'reason': 'PAN missing'}
    if not case.get('aadhaar_last4'):
        return {'valid': False, 'reason': 'Aadhaar last 4 digits missing'}
    if not case.get('name'):
        return {'valid': False, 'reason': 'Name missing'}
    return {'valid': True, 'reason': 'All checks passed'}

def risk_score(case):
    """Compute risk score based on income. Returns int."""
    income = case.get('income', 0)
    if income < 30000:
        return 70
    elif income < 100000:
        return 40
    else:
        return 20

def approval_decision(case):
    """Return approval decision: 'approve', 'manual_review', or 'reject'."""
    validation = validate_kyc(case)
    if not validation['valid']:
        return {'decision': 'manual_review', 'reason': validation['reason']}
    risk = risk_score(case)
    if risk >= 60:
        return {'decision': 'manual_review', 'reason': 'High risk score'}
    return {'decision': 'approve', 'reason': 'Low risk, KYC valid'}
