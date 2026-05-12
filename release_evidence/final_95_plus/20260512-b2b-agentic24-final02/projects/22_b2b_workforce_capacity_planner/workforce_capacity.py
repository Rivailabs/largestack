def capacity_plan(demand, capacity):
    """
    Compare demand hours to available capacity by role.
    Returns dict with role -> {'gap_hours': int, 'status': str}.
    """
    cap_by_role = {c['role']: c['fte'] * c['hours_per_fte'] for c in capacity}
    plan = {}
    for d in demand:
        role = d['role']
        demand_hours = d['hours']
        available = cap_by_role.get(role, 0)
        gap = demand_hours - available
        if gap > 0:
            status = 'overloaded'
        else:
            status = 'ok'
        plan[role] = {'gap_hours': gap, 'status': status}
    return plan


def hiring_recommendation(plan):
    """
    Recommend hiring for overloaded roles.
    No protected-class logic.
    """
    roles = []
    for role, info in plan.items():
        if info['status'] == 'overloaded':
            roles.append({'role': role, 'recommendation': 'hire', 'gap_hours': info['gap_hours']})
    return {'roles': roles}
