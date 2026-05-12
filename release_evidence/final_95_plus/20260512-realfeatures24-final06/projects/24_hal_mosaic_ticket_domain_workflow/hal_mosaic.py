import re

DOMAIN_KEYWORDS = {
    'mosaic_avionics': ['avionics', 'safety', 'production', 'write']
}

def classify_ticket(text: str) -> dict:
    """Classify a ticket text into a domain."""
    text_lower = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if all(kw in text_lower for kw in keywords):
            return {'domain': domain, 'text': text}
    return {'domain': 'general', 'text': text}

def route_ticket(classification: dict) -> dict:
    """Route a ticket based on its classification."""
    domain = classification.get('domain', '')
    if domain == 'mosaic_avionics':
        return {'approval_required': True, 'route': 'specialist/manual approval'}
    return {'approval_required': False, 'route': 'auto'}

def sla_minutes(classification: dict) -> int:
    """Return SLA in minutes for a given classification."""
    domain = classification.get('domain', '')
    if domain == 'mosaic_avionics':
        return 240
    return 480
