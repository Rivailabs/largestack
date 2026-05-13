import pytest
from lead_capture import capture_lead, qualify_lead, export_csv

def test_capture_lead_valid():
    lead = capture_lead('A', 'a@example.com', consent=True, company='Acme')
    assert lead['name'] == 'A'
    assert lead['email'] == 'a@example.com'
    assert lead['consent'] is True
    assert lead['company'] == 'Acme'

def test_capture_lead_missing_consent():
    with pytest.raises(ValueError, match="Consent is required"):
        capture_lead('B', 'b@example.com', consent=False)

def test_capture_lead_invalid_email():
    with pytest.raises(ValueError, match="Invalid email"):
        capture_lead('C', 'invalid', consent=True)

def test_qualify_lead_qualified():
    lead = capture_lead('A', 'a@example.com', consent=True, company='Acme')
    result = qualify_lead(lead)
    assert result['qualified'] is True
    assert result['lead'] == lead

def test_qualify_lead_not_qualified():
    lead = {'name': 'B', 'email': '', 'consent': False, 'company': ''}
    result = qualify_lead(lead)
    assert result['qualified'] is False

def test_export_csv():
    lead = capture_lead('A', 'a@example.com', consent=True, company='Acme')
    csv_output = export_csv([lead])
    assert 'a@example.com' in csv_output
    assert 'name,email,consent,company' in csv_output

def test_export_csv_empty():
    assert export_csv([]) == ''
