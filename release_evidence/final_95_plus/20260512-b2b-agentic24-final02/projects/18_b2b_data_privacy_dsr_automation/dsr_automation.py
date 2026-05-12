import re

def classify_request(req: dict) -> dict:
    """Classify a DSR request into request types."""
    text = req.get('text', '').lower()
    types = set()
    if 'access' in text or 'view' in text:
        types.add('access')
    if 'export' in text or 'download' in text:
        types.add('export')
    if 'delete' in text or 'remove' in text or 'erasure' in text:
        types.add('delete')
    return {'request_types': list(types)}

def fulfillment_plan(req: dict, cls: dict) -> dict:
    """Determine fulfillment plan based on request and classification."""
    identity_verified = req.get('identity_verified', False)
    request_types = cls.get('request_types', [])
    approval_required = 'delete' in request_types
    executed = identity_verified and not approval_required
    return {
        'approval_required': approval_required,
        'executed': executed
    }

def redaction_check(text: str) -> str:
    """Redact email addresses from the given text."""
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    return re.sub(email_pattern, '[REDACTED]', text)
