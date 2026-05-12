from procurement_triage import extract_obligations, flag_contract_risks, approval_route

def test_public_usage_contract():
    text = 'Agreement auto-renews annually. Payment terms Net 15. No liability cap is stated. DPA not attached. Governing law Mars.'
    ob = extract_obligations(text)
    assert ob['payment_terms'] == 'Net 15' and ob['auto_renewal'] is True, ob
    risks = flag_contract_risks(text)
    assert 'missing_liability_cap' in risks and 'missing_dpa' in risks, risks
    route = approval_route(risks)
    assert route['approval_required'] is True and route['executed'] is False, route

def test_no_risks():
    text = 'Payment terms Net 30. Governing law Delaware.'
    risks = flag_contract_risks(text)
    assert risks == []
    route = approval_route(risks)
    assert route['approval_required'] is False and route['executed'] is True

def test_liability_cap_absent_phrase():
    text = 'without liability cap'
    risks = flag_contract_risks(text)
    assert 'missing_liability_cap' in risks

def test_dpa_not_attached():
    text = 'DPA not attached'
    risks = flag_contract_risks(text)
    assert 'missing_dpa' in risks

def test_non_standard_governing_law():
    text = 'Governing law Mars.'
    risks = flag_contract_risks(text)
    assert 'non_standard_governing_law' in risks
