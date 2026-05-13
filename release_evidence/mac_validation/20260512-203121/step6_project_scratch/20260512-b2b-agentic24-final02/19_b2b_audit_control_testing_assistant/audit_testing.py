import json
import os
import random

# Deterministic risk sampling: higher risk score = more likely to be sampled.
# Risk score based on amount and approval status.

def _risk_score(txn):
    score = 0
    # Large amounts increase risk
    if txn.get('amount', 0) > 50000:
        score += 3
    elif txn.get('amount', 0) > 10000:
        score += 2
    else:
        score += 1
    # Unapproved transactions increase risk
    if not txn.get('approved', True):
        score += 2
    return score

def sample_transactions(transactions, limit=2):
    """
    Deterministically sample transactions by risk.
    Returns a list of up to `limit` transactions with highest risk scores.
    If tie, stable sort by id.
    """
    scored = [(txn, _risk_score(txn)) for txn in transactions]
    # Sort by risk descending, then by id ascending for determinism
    scored.sort(key=lambda x: (-x[1], x[0].get('id', '')))
    return [txn for txn, _ in scored[:limit]]

def evaluate_control(sample, rule='large_transactions_require_approval'):
    """
    Evaluate control evidence for a sample of transactions.
    Returns dict with 'status', 'exceptions', 'summary'.
    """
    if rule == 'large_transactions_require_approval':
        exceptions = []
        for txn in sample:
            # Rule: any transaction with amount > 50000 must be approved
            if txn.get('amount', 0) > 50000 and not txn.get('approved', False):
                exceptions.append({
                    'id': txn.get('id'),
                    'amount': txn.get('amount'),
                    'approved': txn.get('approved'),
                    'issue': 'Large transaction without approval'
                })
        status = 'fail' if exceptions else 'pass'
        return {
            'status': status,
            'exceptions': exceptions,
            'summary': f"Found {len(exceptions)} exception(s) in sample of {len(sample)} transactions."
        }
    else:
        return {
            'status': 'unknown',
            'exceptions': [],
            'summary': f"Rule '{rule}' not recognized."
        }
