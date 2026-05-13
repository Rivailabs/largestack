import pytest
from aml_monitoring import screen_transaction, draft_sar, policy_answer

def test_screen_transaction_sanctions():
    txn = {'transaction_id': 'T1', 'amount': 1000, 'country': 'IR', 'counterparty_country': 'US', 'description': 'normal'}
    customer = {'customer_id': 'C1', 'average_monthly_volume': 500}
    watchlist = {'blocked_countries': ['IR'], 'high_risk_keywords': []}
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk_level'] == 'high'
    assert result['risk'] == True
    assert result['requires_review'] == True
    assert any('sanctioned' in r for r in result['reasons'])

def test_screen_transaction_amount_spike():
    txn = {'transaction_id': 'T2', 'amount': 10000, 'country': 'US', 'counterparty_country': 'US', 'description': 'normal'}
    customer = {'customer_id': 'C2', 'avg_monthly_volume': 1000}
    watchlist = {'blocked_countries': [], 'high_risk_keywords': []}
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk_level'] == 'high'
    assert 'exceeds 5x' in result['reasons'][0]

def test_screen_transaction_keyword():
    txn = {'transaction_id': 'T3', 'amount': 100, 'country': 'US', 'counterparty_country': 'US', 'description': 'sanctions related'}
    customer = {'customer_id': 'C3', 'average_monthly_volume': 100}
    watchlist = {'blocked_countries': [], 'high_risk_keywords': ['sanctions']}
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk_level'] == 'high'
    assert 'sanctions' in result['reasons'][0]

def test_screen_transaction_kyc():
    txn = {'transaction_id': 'T4', 'amount': 100, 'country': 'US', 'counterparty_country': 'US', 'description': 'normal'}
    customer = {'customer_id': 'C4', 'average_monthly_volume': 100, 'kyc_score': 85}
    watchlist = {'blocked_countries': [], 'high_risk_keywords': []}
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk_level'] == 'high'
    assert 'KYC' in result['reasons'][0]

def test_screen_transaction_low_risk():
    txn = {'transaction_id': 'T5', 'amount': 100, 'country': 'US', 'counterparty_country': 'US', 'description': 'normal'}
    customer = {'customer_id': 'C5', 'average_monthly_volume': 100, 'kyc_score': 30}
    watchlist = {'blocked_countries': [], 'high_risk_keywords': []}
    result = screen_transaction(txn, customer, watchlist)
    assert result['risk_level'] == 'low'
    assert result['risk'] == False
    assert result['requires_review'] == False

def test_draft_sar_high_risk():
    screening = {'risk_level': 'high'}
    result = draft_sar({'transaction_id': 'T1'}, screening)
    assert result['filed'] == False
    assert result['approval_required'] == True
    assert result['requires_review'] == True

def test_draft_sar_low_risk():
    screening = {'risk_level': 'low'}
    result = draft_sar({'transaction_id': 'T2'}, screening)
    assert result['filed'] == False
    assert result['approval_required'] == False
    assert result['requires_review'] == False

def test_policy_answer_dict_documents():
    docs = {'aml_policy.md': 'All transactions must be screened for sanctions.'}
    result = policy_answer('What about sanctions?', docs)
    assert 'sanctions' in result['answer']
    assert 'aml_policy.md' in result['citations']

def test_policy_answer_list_documents():
    docs = ['All transactions must be screened for sanctions.']
    result = policy_answer('What about sanctions?', docs)
    assert 'sanctions' in result['answer']
    assert len(result['citations']) > 0

def test_policy_answer_unrelated():
    docs = {'aml_policy.md': 'All transactions must be screened for sanctions.'}
    result = policy_answer('equity refresh policy', docs)
    assert result['answer'] == 'Insufficient evidence to answer.'
    assert result['citations'] == []
