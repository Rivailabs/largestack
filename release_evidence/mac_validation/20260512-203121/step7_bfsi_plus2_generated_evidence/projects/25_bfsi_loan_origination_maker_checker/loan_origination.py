def assess_application(applicant):
    """
    Validate applicant data and return decision.
    Returns dict with decision, reasons, and risk_band.
    """
    required = ['applicant_id', 'annual_income', 'monthly_debt', 'credit_score', 'kyc_status', 'requested_amount']
    missing = [k for k in required if k not in applicant]
    if missing:
        return {'decision': 'manual_review', 'reasons': [f'Missing field: {k}' for k in missing], 'risk_band': 'high'}

    annual_income = applicant['annual_income']
    monthly_debt = applicant['monthly_debt']
    credit_score = applicant['credit_score']
    kyc_status = applicant['kyc_status']
    requested_amount = applicant['requested_amount']
    dpd_days = applicant.get('dpd_days', 0)

    reasons = []

    if kyc_status != 'verified':
        reasons.append('KYC not verified')
    if credit_score < 700:
        reasons.append('Credit score below 700')
    debt_to_income = monthly_debt * 12 / annual_income if annual_income > 0 else float('inf')
    if debt_to_income > 0.45:
        reasons.append('Debt-to-income ratio exceeds 0.45')
    if requested_amount > annual_income * 4:
        reasons.append('Requested amount exceeds 4x annual income')
    if dpd_days != 0:
        reasons.append('Has days past due')

    if not reasons:
        return {'decision': 'eligible', 'reasons': [], 'risk_band': 'low'}
    else:
        return {'decision': 'manual_review', 'reasons': reasons, 'risk_band': 'high'}


def create_approval_plan(applicant, assessment):
    """
    Create approval plan. Never disburses funds.
    Returns dict with executed, approval_required, maker_checker, risk_band.
    """
    decision = assessment.get('decision', 'manual_review')
    requested_amount = applicant.get('requested_amount', 0)
    risk_band = assessment.get('risk_band', 'high')

    if decision == 'manual_review' or requested_amount >= 1000000:
        return {
            'executed': False,
            'approval_required': True,
            'maker_checker': ['maker', 'checker'],
            'risk_band': risk_band
        }
    else:
        return {
            'executed': False,
            'approval_required': False,
            'maker_checker': [],
            'risk_band': risk_band
        }
