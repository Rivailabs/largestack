import pytest
from booking import create_slot, book_slot, cancel_booking, list_available, _clear

def setup_function():
    _clear()

def test_create_slot():
    s = create_slot('2026-05-12T10:00', 'Dr A')
    assert s['datetime'] == '2026-05-12T10:00'
    assert s['doctor'] == 'Dr A'
    assert s['booked'] == False
    assert s['patient_email'] is None

def test_book_slot():
    s = create_slot('2026-05-12T10:00', 'Dr A')
    b = book_slot(s['id'], 'patient@example.com')
    assert b['status'] == 'booked'
    assert b['patient_email'] == 'patient@example.com'

def test_double_booking_fails():
    s = create_slot('2026-05-12T10:00', 'Dr A')
    book_slot(s['id'], 'patient1@example.com')
    with pytest.raises(ValueError, match="already booked"):
        book_slot(s['id'], 'patient2@example.com')

def test_cancel_booking():
    s = create_slot('2026-05-12T10:00', 'Dr A')
    book_slot(s['id'], 'patient@example.com')
    c = cancel_booking(s['id'])
    assert c['status'] == 'cancelled'

def test_list_available():
    s1 = create_slot('2026-05-12T10:00', 'Dr A')
    s2 = create_slot('2026-05-12T11:00', 'Dr B')
    book_slot(s1['id'], 'patient@example.com')
    available = list_available()
    assert len(available) == 1
    assert available[0]['id'] == s2['id']

def test_public_contract():
    s = create_slot('2026-05-12T10:00', 'Dr A')
    b = book_slot(s['id'], 'patient@example.com')
    assert b['status'] == 'booked'
    assert list_available() == []
