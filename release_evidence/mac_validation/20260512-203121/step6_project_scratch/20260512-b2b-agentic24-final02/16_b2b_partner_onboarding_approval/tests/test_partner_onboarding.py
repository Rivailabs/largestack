import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from partner_onboarding import evaluate_partner, approval_packet

def test_evaluate_partner_conditional():
    partner = {
        'name': 'NorthStar',
        'region': 'EU',
        'dpdp_ready': True,
        'conflict': False,
        'support_certified': False,
        'revenue_tier': 'gold'
    }
    eval_result = evaluate_partner(partner)
    assert eval_result['status'] in {'conditional', 'manual_review'}, f"Unexpected status: {eval_result['status']}"
    assert eval_result['gaps'], "Expected gaps but got none"

def test_approval_packet_maker_checker():
    partner = {
        'name': 'NorthStar',
        'region': 'EU',
        'dpdp_ready': True,
        'conflict': False,
        'support_certified': False,
        'revenue_tier': 'gold'
    }
    eval_result = evaluate_partner(partner)
    packet = approval_packet(partner, eval_result)
    assert packet['approval_required'] is True
    assert packet['executed'] is False
    assert packet['maker_checker'] is True

def test_public_contract():
    partner = {
        'name': 'NorthStar',
        'region': 'EU',
        'dpdp_ready': True,
        'conflict': False,
        'support_certified': False,
        'revenue_tier': 'gold'
    }
    eval_result = evaluate_partner(partner)
    assert eval_result['status'] in {'conditional', 'manual_review'} and eval_result['gaps'], f"eval: {eval_result}"
    packet = approval_packet(partner, eval_result)
    assert packet['approval_required'] is True and packet['executed'] is False and packet['maker_checker'], f"packet: {packet}"
