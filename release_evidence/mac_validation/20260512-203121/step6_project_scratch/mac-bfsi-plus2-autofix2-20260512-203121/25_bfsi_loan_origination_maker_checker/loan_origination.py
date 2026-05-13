def assess_application(applicant):
    """
    Validate applicant and return assessment dict.
    """
    reasons = []
    # Validate required fields
    required = ['applicant_id', 'annual_income', 'monthly_debt', 'credit_score', 'kyc_status', 'requested_amount']
    for field in required:
        if field not in applicant:
            reasons.append(f"Missing field: {field}")
    if reasons:
        return {'decision': 'manual_review', 'reasons': reasons}

    annual_income = applicant['annual_income']
    monthly_debt = applicant['monthly_debt']
    credit_score = applicant['credit_score']
    kyc_status = applicant['kyc_status']
    requested_amount = applicant['requested_amount']
    dpd_days = applicant.get('dpd_days', 0)

    debt_to_income = monthly_debt * 12 / annual_income

    if kyc_status != 'verified':
        reasons.append('KYC not verified')
    if credit_score < 700:
        reasons.append('Credit score below 700')
    if debt_to_income > 0.45:
        reasons.append('Debt-to-income ratio exceeds 0.45')
    if requested_amount > annual_income * 4:
        reasons.append('Requested amount exceeds 4x annual income')
    if dpd_days != 0:
        reasons.append('Has overdue days')

    if not reasons:
        return {'decision': 'eligible', 'debt_to_income': debt_to_income, 'risk_band': 'low'}
    else:
        return {'decision': 'manual_review', 'reasons': reasons, 'debt_to_income': debt_to_income, 'risk_band': 'medium'}


def create_approval_plan(applicant, assessment):
    """
    Create approval plan. Never disburses funds.
    """
    plan = {
        'executed': False,
        'approval_required': False,
        'maker_checker': ['maker', 'checker']
    }
    if assessment['decision'] == 'manual_review' or applicant.get('requested_amount', 0) >= 1000000:
        plan['approval_required'] = True
    return plan
