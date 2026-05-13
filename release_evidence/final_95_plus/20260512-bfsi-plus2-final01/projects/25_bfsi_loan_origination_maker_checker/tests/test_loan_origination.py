import pytest
from loan_origination import assess_application, create_approval_plan


def test_assess_application_eligible():
    applicant = {
        'applicant_id': '123',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 750,
        'kyc_status': 'verified',
        'requested_amount': 300000,
        'dpd_days': 0
    }
    result = assess_application(applicant)
    assert result['decision'] == 'eligible'
    assert result['reasons'] == []
    assert result['risk_band'] == 'low'


def test_assess_application_manual_review_kyc():
    applicant = {
        'applicant_id': '124',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 750,
        'kyc_status': 'pending',
        'requested_amount': 300000,
        'dpd_days': 0
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert 'KYC not verified' in result['reasons']
    assert result['risk_band'] == 'high'


def test_assess_application_manual_review_credit():
    applicant = {
        'applicant_id': '125',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 650,
        'kyc_status': 'verified',
        'requested_amount': 300000,
        'dpd_days': 0
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert 'Credit score below 700' in result['reasons']
    assert result['risk_band'] == 'high'


def test_assess_application_manual_review_dti():
    applicant = {
        'applicant_id': '126',
        'annual_income': 100000,
        'monthly_debt': 5000,
        'credit_score': 750,
        'kyc_status': 'verified',
        'requested_amount': 300000,
        'dpd_days': 0
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert 'Debt-to-income ratio exceeds 0.45' in result['reasons']
    assert result['risk_band'] == 'high'


def test_assess_application_manual_review_amount():
    applicant = {
        'applicant_id': '127',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 750,
        'kyc_status': 'verified',
        'requested_amount': 500000,
        'dpd_days': 0
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert 'Requested amount exceeds 4x annual income' in result['reasons']
    assert result['risk_band'] == 'high'


def test_assess_application_manual_review_dpd():
    applicant = {
        'applicant_id': '128',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 750,
        'kyc_status': 'verified',
        'requested_amount': 300000,
        'dpd_days': 5
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert 'Has days past due' in result['reasons']
    assert result['risk_band'] == 'high'


def test_assess_application_missing_field():
    applicant = {
        'applicant_id': '129',
        'annual_income': 100000,
        'monthly_debt': 2000,
        'credit_score': 750,
        'kyc_status': 'verified'
        # missing requested_amount
    }
    result = assess_application(applicant)
    assert result['decision'] == 'manual_review'
    assert any('Missing field' in r for r in result['reasons'])
    assert result['risk_band'] == 'high'


def test_create_approval_plan_eligible():
    applicant = {'requested_amount': 500000}
    assessment = {'decision': 'eligible', 'risk_band': 'low'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['executed'] == False
    assert plan['approval_required'] == False
    assert plan['maker_checker'] == []
    assert plan['risk_band'] == 'low'


def test_create_approval_plan_manual_review():
    applicant = {'requested_amount': 500000}
    assessment = {'decision': 'manual_review', 'risk_band': 'high'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['executed'] == False
    assert plan['approval_required'] == True
    assert plan['maker_checker'] == ['maker', 'checker']
    assert plan['risk_band'] == 'high'


def test_create_approval_plan_high_amount():
    applicant = {'requested_amount': 2000000}
    assessment = {'decision': 'eligible', 'risk_band': 'low'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['executed'] == False
    assert plan['approval_required'] == True
    assert plan['maker_checker'] == ['maker', 'checker']
    assert plan['risk_band'] == 'low'
