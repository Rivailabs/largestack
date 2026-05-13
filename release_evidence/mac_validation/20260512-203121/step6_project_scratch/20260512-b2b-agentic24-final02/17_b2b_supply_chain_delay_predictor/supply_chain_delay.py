import json
import os

def predict_delay(shipment: dict) -> dict:
    """
    Estimate delay risk from supplier reliability, port congestion, inventory cover,
    demand spike, and criticality.
    Returns dict with risk_level and delay_days_estimate.
    """
    supplier_score = shipment.get('supplier_score', 100)
    port_congestion = shipment.get('port_congestion', 'low')
    inventory_days = shipment.get('inventory_days', 30)
    demand_spike = shipment.get('demand_spike', False)
    criticality = shipment.get('criticality', 'low')

    risk_score = 0

    # Supplier reliability (lower score = higher risk)
    if supplier_score < 60:
        risk_score += 30
    elif supplier_score < 80:
        risk_score += 15

    # Port congestion
    if port_congestion == 'high':
        risk_score += 30
    elif port_congestion == 'medium':
        risk_score += 15

    # Inventory cover (fewer days = higher risk)
    if inventory_days < 7:
        risk_score += 25
    elif inventory_days < 14:
        risk_score += 10

    # Demand spike
    if demand_spike:
        risk_score += 20

    # Criticality
    if criticality == 'high':
        risk_score += 15
    elif criticality == 'medium':
        risk_score += 5

    # Determine risk level and delay estimate
    if risk_score >= 70:
        risk_level = 'high'
        delay_days = max(7, risk_score // 10)
    elif risk_score >= 40:
        risk_level = 'medium'
        delay_days = max(3, risk_score // 10)
    else:
        risk_level = 'low'
        delay_days = max(0, risk_score // 10)

    return {
        'risk_level': risk_level,
        'delay_days_estimate': delay_days
    }


def mitigation_plan(shipment: dict, risk: dict) -> dict:
    """
    Generate a mitigation plan based on shipment and risk.
    Returns dict with actions list and approval_required boolean.
    """
    actions = []
    approval_required = False

    if risk['risk_level'] == 'high':
        approval_required = True
        actions.append('Expedite shipping via air freight')
        actions.append('Activate backup supplier')
        actions.append('Increase safety stock')
    elif risk['risk_level'] == 'medium':
        actions.append('Monitor shipment closely')
        actions.append('Consider partial air freight')
        if shipment.get('criticality') == 'high':
            approval_required = True
            actions.append('Prepare escalation to management')
    else:
        actions.append('No immediate action needed')

    return {
        'actions': actions,
        'approval_required': approval_required
    }
