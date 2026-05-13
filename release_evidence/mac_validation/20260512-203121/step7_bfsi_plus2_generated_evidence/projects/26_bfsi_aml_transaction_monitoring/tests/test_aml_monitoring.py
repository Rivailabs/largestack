import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from aml_monitoring import screen_transaction, draft_sar, policy_answer

def test_screen_transaction_sanctions():
    txn = {'amount': 50000, 'currency': 'USD', 'counterparty_country': 'IR', 'date': '2025-03-01'}
    customer = {'avg_monthly_volume': 5000, 'kyc_risk': 'low'}
    watchlist = [{'entity': 'Iran', 'type': 'sanctions_country'}]
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk'] == 'high'
    assert any('sanctioned' in r.lower() for r in result['reasons'])

def test_screen_transaction_amount_spike():
    txn = {'amount': 60000, 'currency': 'USD', 'counterparty_country': 'US', 'date': '2025-03-01'}
    customer = {'avg_monthly_volume': 10000, 'kyc_risk': 'low'}
    watchlist = []
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk'] == 'high'
    assert any('exceeds' in r.lower() for r in result['reasons'])

def test_screen_transaction_keyword():
    txn = {'amount': 1000, 'currency': 'USD', 'counterparty_country': 'US', 'date': '2025-03-01', 'description': 'Possible money laundering activity'}
    customer = {'avg_monthly_volume': 5000, 'kyc_risk': 'low'}
    watchlist = []
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk'] == 'high'
    assert any('keyword' in r.lower() for r in result['reasons'])

def test_screen_transaction_kyc_high():
    txn = {'amount': 100, 'currency': 'USD', 'counterparty_country': 'US', 'date': '2025-03-01'}
    customer = {'avg_monthly_volume': 5000, 'kyc_risk': 'high'}
    watchlist = []
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk'] == 'high'
    assert any('kyc' in r.lower() for r in result['reasons'])

def test_screen_transaction_low_risk():
    txn = {'amount': 100, 'currency': 'USD', 'counterparty_country': 'US', 'date': '2025-03-01'}
    customer = {'avg_monthly_volume': 5000, 'kyc_risk': 'low'}
    watchlist = []
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk'] == 'low'

def test_draft_sar_high_risk():
    txn = {'amount': 50000, 'currency': 'USD', 'counterparty_country': 'IR', 'date': '2025-03-01'}
    screening = {'risk': 'high', 'reasons': ['Sanctions country']}
    result = draft_sar(txn, screening)
    assert 'SAR' in result['draft']
    assert result['filed'] == False
    assert result['approval_required'] == True

def test_draft_sar_low_risk():
    txn = {'amount': 100, 'currency': 'USD', 'counterparty_country': 'US', 'date': '2025-03-01'}
    screening = {'risk': 'low', 'reasons': []}
    result = draft_sar(txn, screening)
    assert result['draft'] == 'No SAR needed.'
    assert result['filed'] == False
    assert result['approval_required'] == False

def test_policy_answer_with_documents():
    docs = [
        "All transactions over $10,000 must be reported.",
        "Suspicious activity reports are filed within 30 days.",
        "Customer due diligence is required for all new accounts."
    ]
    result = policy_answer("What is the threshold for reporting?", docs)
    assert 'answer' in result
    assert 'citations' in result
    assert len(result['citations']) > 0

def test_policy_answer_insufficient_evidence():
    docs = [
        "The sky is blue.",
        "Water is wet."
    ]
    result = policy_answer("What is the AML reporting threshold?", docs)
    assert result['answer'] == 'Insufficient evidence to answer.'
    assert result['citations'] == []

def test_policy_answer_no_documents():
    result = policy_answer("What is the threshold?", [])
    assert result['answer'] == 'Insufficient evidence to answer.'
    assert result['citations'] == []
