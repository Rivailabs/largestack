import sys
sys.path.insert(0, '.')
from field_dispatch import schedule_jobs, explain_assignment

def test_schedule_jobs_basic():
    techs = [
        {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 4},
        {'id': 'T2', 'skills': ['network'], 'region': 'south', 'available_hours': 2}
    ]
    jobs = [
        {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'},
        {'id': 'J2', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'low'}
    ]
    schedule = schedule_jobs(techs, jobs)
    assert schedule['assignments'][0]['job_id'] == 'J1'
    assert len(schedule['unassigned']) > 0

def test_explain_assignment_contains_capacity():
    techs = [
        {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 4},
        {'id': 'T2', 'skills': ['network'], 'region': 'south', 'available_hours': 2}
    ]
    jobs = [
        {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'},
        {'id': 'J2', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'low'}
    ]
    schedule = schedule_jobs(techs, jobs)
    explain = explain_assignment(schedule)
    assert 'capacity' in explain.lower() or 'available' in explain.lower()

def test_schedule_jobs_no_overbooking():
    techs = [
        {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 4}
    ]
    jobs = [
        {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'},
        {'id': 'J2', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'low'}
    ]
    schedule = schedule_jobs(techs, jobs)
    # Only one job can be assigned due to hours
    assert len(schedule['assignments']) == 1
    assert len(schedule['unassigned']) == 1

def test_schedule_jobs_priority():
    techs = [
        {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 10}
    ]
    jobs = [
        {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'low'},
        {'id': 'J2', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'}
    ]
    schedule = schedule_jobs(techs, jobs)
    # High priority job should be assigned first
    assert schedule['assignments'][0]['job_id'] == 'J2'
    assert schedule['assignments'][1]['job_id'] == 'J1'

def test_explain_assignment_skipped_jobs():
    techs = [
        {'id': 'T1', 'skills': ['hvac'], 'region': 'north', 'available_hours': 2}
    ]
    jobs = [
        {'id': 'J1', 'skill': 'hvac', 'region': 'north', 'duration_hours': 3, 'priority': 'high'}
    ]
    schedule = schedule_jobs(techs, jobs)
    explain = explain_assignment(schedule)
    assert 'not assigned' in explain
    assert 'capacity' in explain.lower() or 'available' in explain.lower()
