import sys
sys.path.insert(0, '.')
from invoice_reconciliation import reconcile_invoice, payment_decision

def test_reconcile_mismatch():
    po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 12, 'unit_price': 100}]}
    receipts = [{'sku': 'A', 'qty': 10}]
    rec = reconcile_invoice(po, invoice, receipts)
    assert rec['status'] == 'mismatch'
    assert any('quantity_variance' in issue for issue in rec['issues'])

def test_payment_decision_requires_approval():
    po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 12, 'unit_price': 100}]}
    receipts = [{'sku': 'A', 'qty': 10}]
    rec = reconcile_invoice(po, invoice, receipts)
    decision = payment_decision(rec)
    assert decision['approval_required'] is True
    assert decision['executed'] is False

def test_reconcile_match():
    po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    receipts = [{'sku': 'A', 'qty': 10}]
    rec = reconcile_invoice(po, invoice, receipts)
    assert rec['status'] == 'match'
    decision = payment_decision(rec)
    assert decision['approval_required'] is False
    assert decision['executed'] is True

def test_overbilling_flag():
    po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 15, 'unit_price': 100}]}
    receipts = [{'sku': 'A', 'qty': 10}]
    rec = reconcile_invoice(po, invoice, receipts)
    assert any('overbilling' in issue for issue in rec['issues'])

def test_missing_receipt_flag():
    po = {'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    invoice = {'invoice_id': 'I1', 'po_id': 'PO1', 'lines': [{'sku': 'A', 'qty': 10, 'unit_price': 100}]}
    receipts = []
    rec = reconcile_invoice(po, invoice, receipts)
    assert any('missing_receipt' in issue for issue in rec['issues'])
