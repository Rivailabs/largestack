# Appointment Booking

A simple appointment booking system with double-booking prevention.

## Run

```bash
python -c "from booking import create_slot, book_slot, list_available; s=create_slot('2026-05-12T10:00','Dr A'); b=book_slot(s['id'],'patient@example.com'); assert b['status']=='booked'; assert list_available()==[]"
```

## Test

```bash
python -m pytest tests/
```

## Largestack Smoke Test

```bash
python -m pytest tests/test_largestack_features.py -v
```

Requires `largestack` package installed.
