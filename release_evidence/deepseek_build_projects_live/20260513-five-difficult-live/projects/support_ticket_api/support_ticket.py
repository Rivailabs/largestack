import re
from collections import Counter

_ticket_counter = Counter()

def handle_ticket(text: str) -> dict:
    """
    Process a support ticket text and return a dict with:
      - category: str
      - approval_required: bool
      - sop: str
      - response: str
    """
    text_lower = text.lower().strip()
    
    # Determine category and approval logic
    is_payment = 'payment' in text_lower
    is_refund = 'refund' in text_lower
    is_login_reset = 'login' in text_lower and 'reset' in text_lower
    
    # Duplicate detection: if payment and refund both present, treat as refund
    if is_payment and is_refund:
        category = 'refund'
        approval_required = True
        # Increment refund counter for duplicate detection (though rule says no first-refund exception)
        _ticket_counter['refund'] += 1
        sop = 'Process refund after approval'
        response = 'Your refund request has been submitted for approval.'
    elif is_refund:
        category = 'refund'
        approval_required = True
        _ticket_counter['refund'] += 1
        sop = 'Process refund after approval'
        response = 'Your refund request has been submitted for approval.'
    elif is_payment:
        category = 'payment'
        approval_required = True
        sop = 'Process payment after approval'
        response = 'Your payment request has been submitted for approval.'
    elif is_login_reset:
        category = 'login_reset'
        approval_required = False
        sop = 'Verify identity before resetting login'
        response = 'Please verify your identity to reset your login.'
    else:
        category = 'general'
        approval_required = False
        sop = 'Handle general inquiry'
        response = 'Your request has been received.'
    
    return {
        'category': category,
        'approval_required': approval_required,
        'sop': sop,
        'response': response
    }
