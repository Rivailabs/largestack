def classify_incident(incident: str) -> str:
    """Classify an incident based on keywords."""
    incident_lower = incident.lower()
    if 'personal data' in incident_lower or 'customer personal data' in incident_lower:
        return 'personal_data_breach'
    return 'other'


def notification_plan(incident: str) -> list:
    """Return a list of notification steps for a personal data breach."""
    incident_lower = incident.lower()
    if 'personal data' in incident_lower or 'customer personal data' in incident_lower:
        return [
            'Notify DPO within 24 hours',
            'Notify affected data subjects',
            'Notify supervisory authority if required'
        ]
    return ['No notification required']


def containment_steps(incident: str) -> list:
    """Return a list of containment steps for a personal data breach."""
    incident_lower = incident.lower()
    if 'personal data' in incident_lower or 'customer personal data' in incident_lower:
        return [
            'Isolate affected systems',
            'Preserve audit logs',
            'Revoke compromised credentials'
        ]
    return ['No containment required']
