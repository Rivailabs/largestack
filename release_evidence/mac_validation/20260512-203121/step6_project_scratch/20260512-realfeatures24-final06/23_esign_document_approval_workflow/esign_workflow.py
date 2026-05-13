import uuid
import json
from datetime import datetime

# In-memory storage for envelopes and audit trail
_envelopes = {}
_audit_trail = []

def create_envelope(document_name: str) -> dict:
    """Create a new envelope with the given document name."""
    envelope_id = str(uuid.uuid4())
    envelope = {
        'id': envelope_id,
        'document': document_name,
        'signers': [],
        'status': 'draft',
        'created_at': datetime.utcnow().isoformat()
    }
    _envelopes[envelope_id] = envelope
    _audit_trail.append({
        'envelope_id': envelope_id,
        'action': 'created',
        'timestamp': datetime.utcnow().isoformat(),
        'details': f'Envelope created for document {document_name}'
    })
    return envelope

def add_signer(envelope_id: str, email: str) -> dict:
    """Add a signer to an existing envelope."""
    envelope = _envelopes.get(envelope_id)
    if not envelope:
        raise ValueError(f'Envelope {envelope_id} not found')
    signer = {'email': email, 'signed': False}
    envelope['signers'].append(signer)
    _audit_trail.append({
        'envelope_id': envelope_id,
        'action': 'signer_added',
        'timestamp': datetime.utcnow().isoformat(),
        'details': f'Signer {email} added'
    })
    return signer

def send_decision(envelope_id: str) -> dict:
    """Attempt to send the envelope. Always returns executed=False and logs approval required."""
    envelope = _envelopes.get(envelope_id)
    if not envelope:
        raise ValueError(f'Envelope {envelope_id} not found')
    # Offline safety: never actually send
    _audit_trail.append({
        'envelope_id': envelope_id,
        'action': 'send_attempt',
        'timestamp': datetime.utcnow().isoformat(),
        'details': 'Approval is required before sending. Envelope not sent.'
    })
    return {'executed': False, 'message': 'Approval required'}

def audit_trail(envelope_id: str) -> list:
    """Return the audit trail entries for a given envelope."""
    return [entry for entry in _audit_trail if entry['envelope_id'] == envelope_id]
