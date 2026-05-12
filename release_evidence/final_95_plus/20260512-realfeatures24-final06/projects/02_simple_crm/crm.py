import json
import os
from typing import Optional

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'contacts.json')


def _load_contacts() -> list:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return []


def _save_contacts(contacts: list):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(contacts, f, indent=2)


def create_contact(email: str, name: str, stage: str = 'lead') -> dict:
    contacts = _load_contacts()
    for c in contacts:
        if c['email'] == email:
            c['name'] = name
            c['stage'] = stage
            _save_contacts(contacts)
            return c
    new_id = max([c['id'] for c in contacts], default=0) + 1
    contact = {'id': new_id, 'email': email, 'name': name, 'stage': stage}
    contacts.append(contact)
    _save_contacts(contacts)
    return contact


def list_contacts() -> list:
    return _load_contacts()


def update_stage(contact_id: int, new_stage: str) -> Optional[dict]:
    contacts = _load_contacts()
    for c in contacts:
        if c['id'] == contact_id:
            c['stage'] = new_stage
            _save_contacts(contacts)
            return c
    return None


def score_lead(contact: dict) -> int:
    # Simple scoring based on name length and stage
    score = min(len(contact.get('name', '')) * 10, 100)
    stage = contact.get('stage', 'lead')
    if stage == 'customer':
        score = min(score + 20, 100)
    elif stage == 'prospect':
        score = min(score + 10, 100)
    return max(0, min(score, 100))
