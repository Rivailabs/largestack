import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sales_call_coach import score_call, coaching_plan


def test_perfect_transcript():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert score['total_score'] == 100, f"Expected 100, got {score['total_score']}"
    assert score['risk_flags'] == [], f"Expected no risk flags, got {score['risk_flags']}"
    plan = coaching_plan(score)
    assert 'Great job' in plan['actions'][0]


def test_empty_transcript():
    transcript = ""
    score = score_call(transcript)
    assert score['total_score'] == 0
    assert len(score['risk_flags']) == 5


def test_risky_transcript():
    transcript = "Customer needs SOC2. Rep discussed timeline but no next step and promised guaranteed ROI."
    score = score_call(transcript)
    assert score['total_score'] < 80, f"Expected <80, got {score['total_score']}"
    assert len(score['risk_flags']) >= 1
    plan = coaching_plan(score)
    assert 'next step' in ' '.join(plan['actions']).lower()


def test_discovery_not_just_statement():
    transcript = "Customer needs SOC2. Rep discussed timeline but no next step and promised guaranteed ROI."
    score = score_call(transcript)
    assert 'missing_discovery' in score['risk_flags']


def test_discovery_present():
    transcript = "What are your needs? Let me address your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_discovery' not in score['risk_flags']


def test_objection_handling_present():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_objection_handling' not in score['risk_flags']


def test_objection_handling_missing():
    transcript = "What are your needs? Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_objection_handling' in score['risk_flags']


def test_pricing_risk_present():
    transcript = "What are your needs? I understand your budget concerns. We guarantee ROI. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'pricing_risk' in score['risk_flags']


def test_pricing_risk_absent():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'pricing_risk' not in score['risk_flags']


def test_next_step_negated():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. No next step. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_next_step' in score['risk_flags']


def test_next_step_present():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_next_step' not in score['risk_flags']


def test_compliance_present():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up. This is not financial advice."
    score = score_call(transcript)
    assert 'missing_compliance' not in score['risk_flags']


def test_compliance_missing():
    transcript = "What are your needs? I understand your budget concerns. Our pricing is competitive. Next step: schedule a follow-up."
    score = score_call(transcript)
    assert 'missing_compliance' in score['risk_flags']


def test_coaching_plan_positive():
    score = {'total_score': 100, 'risk_flags': [], 'details': {}}
    plan = coaching_plan(score)
    assert 'Great job' in plan['actions'][0]


def test_coaching_plan_improvement():
    score = {'total_score': 60, 'risk_flags': ['missing_discovery', 'missing_next_step'], 'details': {}}
    plan = coaching_plan(score)
    assert len(plan['actions']) == 2
    assert 'discovery' in plan['actions'][0].lower()
    assert 'next step' in plan['actions'][1].lower()
