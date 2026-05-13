import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from supply_chain_delay import predict_delay, mitigation_plan

def test_predict_delay_high_risk():
    shipment = {
        'supplier_score': 55,
        'port_congestion': 'high',
        'inventory_days': 5,
        'demand_spike': True,
        'criticality': 'high'
    }
    risk = predict_delay(shipment)
    assert risk['risk_level'] == 'high'
    assert risk['delay_days_estimate'] >= 7

def test_mitigation_plan_high_risk():
    shipment = {
        'supplier_score': 55,
        'port_congestion': 'high',
        'inventory_days': 5,
        'demand_spike': True,
        'criticality': 'high'
    }
    risk = predict_delay(shipment)
    plan = mitigation_plan(shipment, risk)
    assert len(plan['actions']) > 0
    assert plan['approval_required'] is True

def test_predict_delay_low_risk():
    shipment = {
        'supplier_score': 85,
        'port_congestion': 'low',
        'inventory_days': 20,
        'demand_spike': False,
        'criticality': 'low'
    }
    risk = predict_delay(shipment)
    assert risk['risk_level'] == 'low'
    assert risk['delay_days_estimate'] >= 0

def test_mitigation_plan_low_risk():
    shipment = {
        'supplier_score': 85,
        'port_congestion': 'low',
        'inventory_days': 20,
        'demand_spike': False,
        'criticality': 'low'
    }
    risk = predict_delay(shipment)
    plan = mitigation_plan(shipment, risk)
    assert len(plan['actions']) > 0
    assert plan['approval_required'] is False

def test_public_contract():
    shipment = {
        'supplier_score': 55,
        'port_congestion': 'high',
        'inventory_days': 5,
        'demand_spike': True,
        'criticality': 'high'
    }
    risk = predict_delay(shipment)
    assert risk['risk_level'] == 'high' and risk['delay_days_estimate'] >= 7, risk
    plan = mitigation_plan(shipment, risk)
    assert plan['actions'] and plan['approval_required'] is True, plan
