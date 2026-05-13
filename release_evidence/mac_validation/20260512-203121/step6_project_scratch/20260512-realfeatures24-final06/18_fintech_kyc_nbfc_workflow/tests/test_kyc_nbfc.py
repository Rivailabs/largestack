from kyc_nbfc import validate_kyc, risk_score, approval_decision

def test_validate_kyc_valid():
    case = {'name': 'A', 'pan': 'ABCDE1234F', 'aadhaar_last4': '1234', 'income': 50000}
    result = validate_kyc(case)
    assert result['valid'] is True

def test_validate_kyc_missing_pan():
    case = {'name': 'A', 'aadhaar_last4': '1234', 'income': 50000}
    result = validate_kyc(case)
    assert result['valid'] is False
    assert 'PAN' in result['reason']

def test_approval_decision_valid():
    case = {'name': 'A', 'pan': 'ABCDE1234F', 'aadhaar_last4': '1234', 'income': 50000}
    result = approval_decision(case)
    assert result['decision'] in {'approve', 'manual_review'}

def test_approval_decision_missing_pan():
    case = {'name': 'B'}
    result = approval_decision(case)
    assert result['decision'] == 'manual_review'

def test_approval_decision_high_risk():
    case = {'name': 'C', 'pan': 'XYZ1234A', 'aadhaar_last4': '5678', 'income': 20000}
    result = approval_decision(case)
    assert result['decision'] == 'manual_review'
