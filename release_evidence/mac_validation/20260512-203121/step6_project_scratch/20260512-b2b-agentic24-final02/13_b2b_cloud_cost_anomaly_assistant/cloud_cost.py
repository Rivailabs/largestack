import math
from typing import List, Dict, Any

def detect_anomalies(usage: List[Dict[str, Any]], threshold: float = 2.0) -> List[Dict[str, Any]]:
    """
    Detect spend spikes against baseline.
    Returns list of anomalies with service, daily_cost, baseline, ratio, and service_drivers.
    """
    anomalies = []
    for entry in usage:
        service = entry.get('service', '')
        daily_cost = entry.get('daily_cost', 0)
        baseline = entry.get('baseline', 1)  # avoid division by zero
        if baseline == 0:
            baseline = 1
        ratio = daily_cost / baseline
        if ratio >= threshold:
            # Determine service drivers based on service type
            if service == 'compute':
                drivers = ['increased instance usage', 'new deployments', 'scaling events']
            elif service == 'storage':
                drivers = ['data ingestion spike', 'backup jobs', 'unexpected writes']
            elif service == 'database':
                drivers = ['query load increase', 'index rebuilds', 'connection surge']
            else:
                drivers = ['unexpected usage pattern']
            anomalies.append({
                'service': service,
                'daily_cost': daily_cost,
                'baseline': baseline,
                'ratio': round(ratio, 2),
                'service_drivers': drivers
            })
    return anomalies

def remediation_plan(anomalies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate remediation plan requiring approval before shutdown/resizing.
    Returns dict with approval_required=True and executed=False.
    """
    if not anomalies:
        return {'approval_required': False, 'executed': False, 'actions': []}
    actions = []
    for anom in anomalies:
        service = anom['service']
        if service == 'compute':
            actions.append({'service': service, 'action': 'resize_instances', 'reason': 'cost spike'})
        elif service == 'storage':
            actions.append({'service': service, 'action': 'reduce_storage', 'reason': 'cost spike'})
        else:
            actions.append({'service': service, 'action': 'review_usage', 'reason': 'cost spike'})
    return {
        'approval_required': True,
        'executed': False,
        'actions': actions
    }
