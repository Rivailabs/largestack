from workforce_capacity import capacity_plan, hiring_recommendation

def test_capacity_plan_overload():
    demand = [{'role':'support','hours':220},{'role':'engineering','hours':120}]
    capacity = [{'role':'support','fte':1,'hours_per_fte':160},{'role':'engineering','fte':1,'hours_per_fte':160}]
    plan = capacity_plan(demand, capacity)
    assert plan['support']['gap_hours'] == 60
    assert plan['support']['status'] == 'overloaded'
    assert plan['engineering']['gap_hours'] == -40
    assert plan['engineering']['status'] == 'ok'

def test_hiring_recommendation():
    demand = [{'role':'support','hours':220},{'role':'engineering','hours':120}]
    capacity = [{'role':'support','fte':1,'hours_per_fte':160},{'role':'engineering','fte':1,'hours_per_fte':160}]
    plan = capacity_plan(demand, capacity)
    rec = hiring_recommendation(plan)
    assert rec['roles'][0]['role'] == 'support'
    assert 'protected' not in str(rec).lower()

def test_no_overload():
    demand = [{'role':'support','hours':100}]
    capacity = [{'role':'support','fte':1,'hours_per_fte':160}]
    plan = capacity_plan(demand, capacity)
    assert plan['support']['status'] == 'ok'
    rec = hiring_recommendation(plan)
    assert rec['roles'] == []
