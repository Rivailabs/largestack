import sys
sys.path.insert(0, '.')
from ar_collections import prioritize_accounts, draft_collection_plan

def test_prioritize_accounts():
    accounts = [
        {'account': 'A', 'amount_due': 50000, 'days_past_due': 45, 'tier': 'strategic', 'disputed': False},
        {'account': 'B', 'amount_due': 5000, 'days_past_due': 5, 'tier': 'standard', 'disputed': False}
    ]
    ranked = prioritize_accounts(accounts)
    assert ranked[0]['account'] == 'A'
    assert ranked[0]['priority_score'] > ranked[1]['priority_score']

def test_draft_collection_plan():
    account = {'account': 'A', 'amount_due': 50000, 'days_past_due': 45, 'tier': 'strategic', 'disputed': False, 'priority_score': 100}
    plan = draft_collection_plan(account)
    assert plan['send_executed'] is False
    assert plan['approval_required'] is True

def test_draft_collection_plan_disputed():
    account = {'account': 'C', 'amount_due': 1000, 'days_past_due': 10, 'tier': 'standard', 'disputed': True, 'priority_score': 50}
    plan = draft_collection_plan(account)
    assert plan['send_executed'] is False
    assert plan['approval_required'] is True
    assert 'Flag for dispute resolution' in plan['actions']
