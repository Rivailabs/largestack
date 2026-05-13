import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from loan_origination import assess_application, create_approval_plan


def test_assess_eligible():
    applicant = {
        "applicant_id": "APP123",
        "annual_income": 60000,
        "monthly_debt": 1000,
        "credit_score": 750,
        "kyc_status": "verified",
        "requested_amount": 50000,
        "dpd_days": 0
    }
    assessment = assess_application(applicant)
    assert assessment['decision'] == 'eligible'
    assert assessment['debt_to_income'] == 0.2


def test_assess_manual_review():
    applicant = {
        "applicant_id": "APP456",
        "annual_income": 60000,
        "monthly_debt": 3000,
        "credit_score": 650,
        "kyc_status": "pending",
        "requested_amount": 300000,
        "dpd_days": 5
    }
    assessment = assess_application(applicant)
    assert assessment['decision'] == 'manual_review'
    assert 'KYC not verified' in assessment['reasons']
    assert 'Credit score below 700' in assessment['reasons']
    assert 'Debt-to-income ratio exceeds 0.45' in assessment['reasons']
    assert 'Requested amount exceeds 4x annual income' in assessment['reasons']
    assert 'Has overdue days' in assessment['reasons']


def test_create_approval_plan_eligible():
    applicant = {"requested_amount": 50000}
    assessment = {'decision': 'eligible'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['executed'] == False
    assert plan['approval_required'] == False
    assert plan['maker_checker'] == ['maker', 'checker']


def test_create_approval_plan_manual_review():
    applicant = {"requested_amount": 50000}
    assessment = {'decision': 'manual_review'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['approval_required'] == True


def test_create_approval_plan_high_amount():
    applicant = {"requested_amount": 1000000}
    assessment = {'decision': 'eligible'}
    plan = create_approval_plan(applicant, assessment)
    assert plan['approval_required'] == True


def test_assess_missing_field():
    applicant = {"applicant_id": "APP789"}
    assessment = assess_application(applicant)
    assert assessment['decision'] == 'manual_review'
    assert 'Missing field: annual_income' in assessment['reasons']