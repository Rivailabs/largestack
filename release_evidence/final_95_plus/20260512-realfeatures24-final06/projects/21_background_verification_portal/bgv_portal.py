import uuid
from datetime import datetime

# In-memory storage
_candidates = {}
_cases = {}


def submit_candidate(name, email, consent=False):
    if not consent:
        raise ValueError("Consent is required for background verification")
    candidate_id = str(uuid.uuid4())
    _candidates[candidate_id] = {
        'name': name,
        'email': email,
        'consent': consent,
        'submitted_at': datetime.utcnow().isoformat()
    }
    _cases[candidate_id] = {
        'status': 'in_progress',
        'documents': []
    }
    return {'id': candidate_id, 'name': name, 'email': email}


def verify_document(candidate_id, doc_type, doc_value):
    if candidate_id not in _candidates:
        raise ValueError("Candidate not found")
    if not _candidates[candidate_id]['consent']:
        raise ValueError("Consent missing")
    # Simple verification logic
    verified = doc_value == 'valid'
    _cases[candidate_id]['documents'].append({
        'type': doc_type,
        'value': doc_value,
        'verified': verified
    })
    if verified:
        _cases[candidate_id]['status'] = 'verified'
    return {'verified': verified, 'doc_type': doc_type}


def case_status(candidate_id):
    if candidate_id not in _cases:
        raise ValueError("Case not found")
    return {'status': _cases[candidate_id]['status']}
