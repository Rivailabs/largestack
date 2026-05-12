import json
import os

def _load_policy():
    policy_path = os.path.join(os.path.dirname(__file__), 'policies', 'compliance_rules.json')
    with open(policy_path) as f:
        return json.load(f)

def evaluate_partner(partner: dict) -> dict:
    policy = _load_policy()
    gaps = []
    status = 'approved'

    # Region validation
    allowed_regions = policy.get('allowed_regions', [])
    if partner.get('region') not in allowed_regions:
        gaps.append('region_not_allowed')
        status = 'manual_review'

    # DPDP readiness (compliance attestation)
    if not partner.get('dpdp_ready'):
        gaps.append('dpdp_not_ready')
        status = 'manual_review'

    # Conflict check
    if partner.get('conflict'):
        gaps.append('conflict_detected')
        status = 'manual_review'

    # Support readiness
    if not partner.get('support_certified'):
        gaps.append('support_not_certified')
        if status == 'approved':
            status = 'conditional'

    # Revenue tier validation
    allowed_tiers = policy.get('allowed_revenue_tiers', [])
    if partner.get('revenue_tier') not in allowed_tiers:
        gaps.append('revenue_tier_not_allowed')
        status = 'manual_review'

    return {'status': status, 'gaps': gaps}

def approval_packet(partner: dict, evaluation: dict) -> dict:
    # Maker-checker gated: approval_required True if any gaps or status not approved
    approval_required = evaluation['status'] != 'approved' or len(evaluation['gaps']) > 0
    return {
        'approval_required': approval_required,
        'executed': False,
        'maker_checker': True
    }
