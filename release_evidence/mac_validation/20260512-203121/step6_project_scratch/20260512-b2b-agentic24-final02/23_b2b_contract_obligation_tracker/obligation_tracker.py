import re
from datetime import datetime, timedelta

def extract_obligations(text: str) -> list:
    """Extract obligations from text. Returns list of dicts with keys: type, owner, due_date, renewal_date, audit_evidence, status."""
    items = []
    # Pattern for obligations: "Vendor must ... by YYYY-MM-DD" or "Customer must ... by YYYY-MM-DD"
    pattern = r'(Vendor|Customer)\s+must\s+(.+?)\s+by\s+(\d{4}-\d{2}-\d{2})'
    matches = re.findall(pattern, text, re.IGNORECASE)
    for match in matches:
        party = match[0].lower()
        obligation = match[1].strip()
        due_date_str = match[2]
        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        # Determine type based on obligation text
        if 'soc2' in obligation.lower():
            typ = 'soc2_report'
        elif 'renew' in obligation.lower():
            typ = 'renewal'
        else:
            typ = obligation.lower().replace(' ', '_')
        # Extract owner from text if present
        owner_match = re.search(r'Owner:\s*(\S+)', text)
        owner = owner_match.group(1).rstrip('.') if owner_match else 'unknown'
        items.append({
            'type': typ,
            'owner': owner,
            'due_date': due_date,
            'renewal_date': due_date if typ == 'renewal' else None,
            'audit_evidence': [],
            'status': 'active'
        })
    return items

def due_soon(items: list, today: str, days: int) -> list:
    """Return items due within `days` from `today`."""
    today_date = datetime.strptime(today, '%Y-%m-%d').date()
    cutoff = today_date + timedelta(days=days)
    return [item for item in items if item['due_date'] <= cutoff and item['due_date'] >= today_date]

def escalation_plan(items: list) -> dict:
    """Generate escalation plan for overdue/high-risk obligations."""
    if not items:
        return {'approval_required': False, 'actions': []}
    # Simple logic: if any item is due within 3 days, require approval
    today = datetime.now().date()
    urgent = any(item['due_date'] <= today + timedelta(days=3) for item in items)
    return {
        'approval_required': urgent,
        'actions': ['notify_owner', 'schedule_review'] if urgent else ['monitor']
    }
