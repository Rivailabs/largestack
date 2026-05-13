import uuid

_slots = {}
_bookings = {}

def create_slot(datetime_str: str, doctor: str) -> dict:
    slot_id = str(uuid.uuid4())
    slot = {
        'id': slot_id,
        'datetime': datetime_str,
        'doctor': doctor,
        'booked': False,
        'patient_email': None
    }
    _slots[slot_id] = slot
    return slot

def book_slot(slot_id: str, patient_email: str) -> dict:
    slot = _slots.get(slot_id)
    if slot is None:
        raise ValueError("Slot not found")
    if slot['booked']:
        raise ValueError("Slot already booked")
    slot['booked'] = True
    slot['patient_email'] = patient_email
    _bookings[slot_id] = slot
    return {'status': 'booked', 'slot_id': slot_id, 'patient_email': patient_email}

def cancel_booking(slot_id: str) -> dict:
    slot = _slots.get(slot_id)
    if slot is None:
        raise ValueError("Slot not found")
    if not slot['booked']:
        raise ValueError("Slot is not booked")
    slot['booked'] = False
    slot['patient_email'] = None
    _bookings.pop(slot_id, None)
    return {'status': 'cancelled', 'slot_id': slot_id}

def list_available() -> list:
    return [slot for slot in _slots.values() if not slot['booked']]

def _clear():
    _slots.clear()
    _bookings.clear()
