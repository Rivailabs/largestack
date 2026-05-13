import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from audit_testing import sample_transactions, evaluate_control

def test_sample_transactions_risk_ordering():
    txns = [
        {'id': '1', 'amount': 1000, 'approved': True},
        {'id': '2', 'amount': 90000, 'approved': False},
        {'id': '3', 'amount': 50000, 'approved': True}
    ]
    sample = sample_transactions(txns, limit=2)
    # Highest risk: id=2 (amount>50000, not approved) then id=3 (amount=50000, approved) or id=1 (low amount, approved)
    # Risk scores: id2=5, id3=3, id1=1 => sample should be [id2, id3]
    assert sample[0]['id'] == '2', f"Expected id=2 first, got {sample}"
    assert sample[1]['id'] == '3', f"Expected id=3 second, got {sample}"

def test_evaluate_control_fail():
    txns = [
        {'id': '1', 'amount': 1000, 'approved': True},
        {'id': '2', 'amount': 90000, 'approved': False},
        {'id': '3', 'amount': 50000, 'approved': True}
    ]
    sample = sample_transactions(txns, limit=2)
    result = evaluate_control(sample, rule='large_transactions_require_approval')
    assert result['exceptions'], f"Expected exceptions, got {result}"
    assert result['status'] == 'fail', f"Expected status fail, got {result}"

def test_evaluate_control_pass():
    txns = [
        {'id': '1', 'amount': 1000, 'approved': True},
        {'id': '3', 'amount': 50000, 'approved': True}
    ]
    result = evaluate_control(txns, rule='large_transactions_require_approval')
    assert not result['exceptions'], f"Expected no exceptions, got {result}"
    assert result['status'] == 'pass', f"Expected status pass, got {result}"

def test_public_contract():
    txns=[{'id':'1','amount':1000,'approved':True},{'id':'2','amount':90000,'approved':False},{'id':'3','amount':50000,'approved':True}]
    sample=sample_transactions(txns, limit=2)
    assert sample[0]['id']=='2', sample
    result=evaluate_control(sample, rule='large_transactions_require_approval')
    assert result['exceptions'] and result['status']=='fail', result
