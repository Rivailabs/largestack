import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obligation_tracker import extract_obligations, due_soon, escalation_plan

def test_extract_obligations():
    text = 'Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'
    items = extract_obligations(text)
    assert any(i['type'] == 'soc2_report' for i in items), f"Items: {items}"

def test_due_soon():
    text = 'Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'
    items = extract_obligations(text)
    soon = due_soon(items, today='2026-05-12', days=10)
    assert soon and soon[0]['owner'] == 'security', f"Soon: {soon}"

def test_escalation_plan():
    text = 'Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'
    items = extract_obligations(text)
    soon = due_soon(items, today='2026-05-12', days=10)
    esc = escalation_plan(soon)
    assert esc['approval_required'] is False and esc['actions'], f"Esc: {esc}"

def test_public_contract():
    text = 'Vendor must deliver SOC2 report by 2026-05-20. Customer must renew by 2026-06-01. Owner: security.'
    items = extract_obligations(text)
    assert any(i['type'] == 'soc2_report' for i in items), items
    soon = due_soon(items, today='2026-05-12', days=10)
    assert soon and soon[0]['owner'] == 'security', soon
    esc = escalation_plan(soon)
    assert esc['approval_required'] is False and esc['actions'], esc
