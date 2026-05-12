import sys
sys.path.insert(0, '.')
from vendor_risk import assess_vendor, approval_requirements, policy_answer

def test_assess_vendor_high_risk():
    vendor = {'name':'DataCo','soc2':False,'dpdp_ready':False,'country':'US','criticality':'high','financial_score':45}
    risk = assess_vendor(vendor)
    assert risk['risk_level'] == 'high'
    assert len(risk['reasons']) >= 2

def test_approval_requirements_high():
    risk = {'risk_level': 'high', 'score': 85, 'reasons': ['test']}
    approval = approval_requirements(risk)
    assert approval['approval_required'] is True
    assert approval['executed'] is False

def test_policy_answer_supported():
    docs = {'vendor_policy.md': 'High criticality vendors without SOC2 require security committee approval.'}
    ans = policy_answer('when security committee approval vendor?', docs)
    assert 'security committee' in ans['answer'].lower()
    assert 'vendor_policy.md' in ans['citations']

def test_policy_answer_insufficient_evidence():
    docs = {'vendor_policy.md': 'High criticality vendors without SOC2 require security committee approval.'}
    ans = policy_answer('office snacks policy', docs)
    assert 'insufficient evidence' in ans['answer'].lower()

def test_assess_vendor_low_risk():
    vendor = {'name':'SafeCo','soc2':True,'dpdp_ready':True,'country':'US','criticality':'low','financial_score':90}
    risk = assess_vendor(vendor)
    assert risk['risk_level'] == 'low'

def test_approval_requirements_low():
    risk = {'risk_level': 'low', 'score': 10, 'reasons': []}
    approval = approval_requirements(risk)
    assert approval['approval_required'] is False
    assert approval['executed'] is False
