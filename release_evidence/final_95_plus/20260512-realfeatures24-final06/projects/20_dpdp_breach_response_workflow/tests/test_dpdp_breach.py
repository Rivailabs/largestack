import pytest
from dpdp_breach import classify_incident, notification_plan, containment_steps


def test_classify_incident():
    inc = 'customer personal data leaked'
    assert classify_incident(inc) == 'personal_data_breach'


def test_notification_plan_contains_dpo():
    inc = 'customer personal data leaked'
    plan = notification_plan(inc)
    assert 'dpo' in ' '.join(plan).lower()


def test_containment_steps_contains_audit():
    inc = 'customer personal data leaked'
    steps = containment_steps(inc)
    assert any('audit' in s.lower() for s in steps)


def test_other_incident():
    inc = 'server down'
    assert classify_incident(inc) == 'other'
    assert notification_plan(inc) == ['No notification required']
    assert containment_steps(inc) == ['No containment required']
