import re

def normalize_lead(lead: dict) -> dict:
    """Normalize email domain and company name."""
    email = lead.get('email', '')
    domain = email.split('@')[-1].strip().lower() if '@' in email else ''
    company = lead.get('company', '').strip()
    # Remove extra spaces and title case
    company = re.sub(r'\s+', ' ', company).strip()
    # Capitalize each word
    company = ' '.join(word.capitalize() for word in company.split())
    lead['domain'] = domain
    lead['company'] = company
    return lead

def route_account(lead: dict) -> dict:
    """Route lead to appropriate queue based on employees and last_touch_days."""
    employees = lead.get('employees', 0)
    last_touch = lead.get('last_touch_days', 0)
    if employees >= 500:
        queue = 'enterprise_ae'
        priority = 'urgent' if last_touch > 7 else 'high'
    elif employees >= 100:
        queue = 'inbound'
        priority = 'normal'
    else:
        queue = 'inbound'
        priority = 'low'
    # Stale high-value leads (enterprise with no touch > 30 days) escalate
    if queue == 'enterprise_ae' and last_touch > 30:
        queue = 'escalation'
        priority = 'urgent'
    return {'queue': queue, 'priority': priority}

def build_sla_plan(lead: dict) -> dict:
    """Build SLA plan. If last_touch_days > 7, escalate with due_hours <= 24."""
    last_touch = lead.get('last_touch_days', 0)
    if last_touch > 7:
        return {'escalate': True, 'due_hours': 24}
    else:
        return {'escalate': False, 'due_hours': 48}
