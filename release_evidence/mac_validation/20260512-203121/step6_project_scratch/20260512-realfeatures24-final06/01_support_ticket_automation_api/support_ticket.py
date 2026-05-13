import re

CATEGORY_KEYWORDS = {
    'refund': ['refund', 'payment', 'duplicate payment'],
    'login_reset': ['login reset', 'reset password', 'forgot password'],
    'security': ['security', 'breach', 'unauthorized'],
    'data_export': ['data export', 'export data', 'download data'],
}

APPROVAL_REQUIRED_CATEGORIES = {'refund', 'payment', 'security', 'data_export'}

def handle_ticket(text: str) -> dict:
    text_lower = text.lower()
    category = 'general'
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                category = cat
                break
        if category != 'general':
            break
    approval_required = category in APPROVAL_REQUIRED_CATEGORIES
    response = ''
    if category == 'login_reset':
        response = 'Identity verification required. Please verify your identity to reset login.'
    elif approval_required:
        response = f'Approval required for {category} request.'
    else:
        response = 'Request received.'
    return {
        'category': category,
        'approval_required': approval_required,
        'response': response
    }
