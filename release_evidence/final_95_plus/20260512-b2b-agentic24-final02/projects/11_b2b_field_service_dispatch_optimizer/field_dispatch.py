from typing import List, Dict, Any

def schedule_jobs(techs: List[Dict[str, Any]], jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Assign technicians to jobs based on skill, region, priority, and available hours.
    Returns a dict with 'assignments' (list of dicts) and 'unassigned' (list of job dicts).
    """
    # Sort jobs by priority: high first, then medium, then low
    priority_order = {'high': 0, 'medium': 1, 'low': 2}
    sorted_jobs = sorted(jobs, key=lambda j: priority_order.get(j.get('priority', 'low'), 2))

    # Track remaining hours per technician
    tech_hours = {t['id']: t['available_hours'] for t in techs}
    assignments = []
    unassigned = []

    for job in sorted_jobs:
        assigned = False
        # Find best technician: matching skill and region, with enough hours, highest priority first
        for tech in techs:
            if (job['skill'] in tech['skills'] and
                job['region'] == tech['region'] and
                tech_hours[tech['id']] >= job['duration_hours']):
                # Assign job to this technician
                assignments.append({
                    'job_id': job['id'],
                    'tech_id': tech['id'],
                    'skill': job['skill'],
                    'region': job['region'],
                    'duration_hours': job['duration_hours'],
                    'priority': job['priority']
                })
                tech_hours[tech['id']] -= job['duration_hours']
                assigned = True
                break
        if not assigned:
            unassigned.append(job)

    return {'assignments': assignments, 'unassigned': unassigned}


def explain_assignment(schedule: Dict[str, Any]) -> str:
    """
    Provide a human-readable explanation of the schedule, including reasons for skipped jobs.
    """
    lines = []
    lines.append(f"Total assignments: {len(schedule['assignments'])}")
    lines.append(f"Unassigned jobs: {len(schedule['unassigned'])}")
    for job in schedule['unassigned']:
        lines.append(f"Job {job['id']} not assigned: insufficient technician capacity or skill/region mismatch.")
    return '\n'.join(lines)
