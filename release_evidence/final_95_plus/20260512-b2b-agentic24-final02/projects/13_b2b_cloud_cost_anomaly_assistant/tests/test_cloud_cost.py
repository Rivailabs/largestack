import pytest
from cloud_cost import detect_anomalies, remediation_plan

def test_detect_anomalies_contract():
    usage = [
        {'service': 'compute', 'daily_cost': 100, 'baseline': 40},
        {'service': 'storage', 'daily_cost': 20, 'baseline': 22}
    ]
    anoms = detect_anomalies(usage, threshold=2.0)
    assert len(anoms) == 1
    assert anoms[0]['service'] == 'compute'
    assert anoms[0]['ratio'] >= 2.5
    assert 'service_drivers' in anoms[0]
    assert isinstance(anoms[0]['service_drivers'], list)

def test_remediation_plan_contract():
    usage = [
        {'service': 'compute', 'daily_cost': 100, 'baseline': 40},
        {'service': 'storage', 'daily_cost': 20, 'baseline': 22}
    ]
    anoms = detect_anomalies(usage, threshold=2.0)
    plan = remediation_plan(anoms)
    assert plan['approval_required'] is True
    assert plan['executed'] is False
    assert 'actions' in plan
    assert len(plan['actions']) > 0

def test_no_anomalies():
    usage = [
        {'service': 'compute', 'daily_cost': 30, 'baseline': 40},
        {'service': 'storage', 'daily_cost': 20, 'baseline': 22}
    ]
    anoms = detect_anomalies(usage, threshold=2.0)
    assert len(anoms) == 0
    plan = remediation_plan(anoms)
    assert plan['approval_required'] is False
    assert plan['executed'] is False

def test_multiple_anomalies():
    usage = [
        {'service': 'compute', 'daily_cost': 100, 'baseline': 40},
        {'service': 'storage', 'daily_cost': 80, 'baseline': 20},
        {'service': 'database', 'daily_cost': 150, 'baseline': 50}
    ]
    anoms = detect_anomalies(usage, threshold=2.0)
    assert len(anoms) == 3
    for anom in anoms:
        assert anom['ratio'] >= 2.0

def test_remediation_plan_actions():
    usage = [
        {'service': 'compute', 'daily_cost': 100, 'baseline': 40},
        {'service': 'storage', 'daily_cost': 80, 'baseline': 20}
    ]
    anoms = detect_anomalies(usage, threshold=2.0)
    plan = remediation_plan(anoms)
    assert plan['approval_required'] is True
    assert plan['executed'] is False
    actions = plan['actions']
    assert len(actions) == 2
    assert actions[0]['service'] == 'compute'
    assert actions[0]['action'] == 'resize_instances'
    assert actions[1]['service'] == 'storage'
    assert actions[1]['action'] == 'reduce_storage'
