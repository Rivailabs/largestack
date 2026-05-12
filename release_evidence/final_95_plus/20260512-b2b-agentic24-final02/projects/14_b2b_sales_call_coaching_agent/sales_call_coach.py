import re

def score_call(transcript: str) -> dict:
    """
    Score a sales call transcript on a 100-point rubric.
    Returns dict with total_score, risk_flags, and details.
    """
    if not transcript or not transcript.strip():
        return {
            'total_score': 0,
            'risk_flags': [
                'missing_discovery',
                'missing_objection_handling',
                'pricing_risk',
                'missing_next_step',
                'missing_compliance'
            ],
            'details': {
                'discovery': False,
                'objection_handling': False,
                'pricing_risk': True,
                'next_step': False,
                'compliance': False
            }
        }

    text_lower = transcript.lower()
    risk_flags = []
    details = {}

    # Discovery: must include explicit question/need phrases
    discovery_phrases = [
        'what are your needs',
        'pain point',
        'business goal',
        'success criteria'
    ]
    discovery_present = any(phrase in text_lower for phrase in discovery_phrases)
    details['discovery'] = discovery_present
    if not discovery_present:
        risk_flags.append('missing_discovery')

    # Objection handling: look for objection-related words
    objection_phrases = [
        'budget', 'timeline', 'concern', 'objection', 'address', 'understand'
    ]
    objection_present = any(phrase in text_lower for phrase in objection_phrases)
    details['objection_handling'] = objection_present
    if not objection_present:
        risk_flags.append('missing_objection_handling')

    # Pricing risk: detect risky promises
    pricing_risk_phrases = [
        'guaranteed roi', 'guarantee roi', 'guaranteed return',
        'promise roi', 'promised roi', 'guaranteed results'
    ]
    pricing_risk = any(phrase in text_lower for phrase in pricing_risk_phrases)
    details['pricing_risk'] = pricing_risk
    if pricing_risk:
        risk_flags.append('pricing_risk')

    # Next step: must be present and not negated
    next_step_phrases = [
        'next step', 'follow up', 'schedule', 'send proposal', 'meeting booked'
    ]
    negation_phrases = [
        'no next step', 'without next step', 'missing next step'
    ]
    next_step_present = any(phrase in text_lower for phrase in next_step_phrases)
    next_step_negated = any(phrase in text_lower for phrase in negation_phrases)
    # If negated, treat as missing even if phrase appears
    if next_step_negated:
        next_step_present = False
    details['next_step'] = next_step_present
    if not next_step_present:
        risk_flags.append('missing_next_step')

    # Compliance disclaimer
    compliance_phrases = [
        'disclaimer', 'compliance', 'not financial advice',
        'this is not financial advice', 'for informational purposes'
    ]
    compliance_present = any(phrase in text_lower for phrase in compliance_phrases)
    details['compliance'] = compliance_present
    if not compliance_present:
        risk_flags.append('missing_compliance')

    total_score = 100 - len(risk_flags) * 20

    return {
        'total_score': total_score,
        'risk_flags': risk_flags,
        'details': details
    }


def coaching_plan(score: dict) -> dict:
    """
    Generate a coaching plan based on the score.
    Returns dict with actions list.
    """
    actions = []
    if not score['risk_flags']:
        actions.append('Great job! Keep up the excellent work.')
    else:
        if 'missing_discovery' in score['risk_flags']:
            actions.append('Practice asking discovery questions like "What are your needs?" or "What is your pain point?"')
        if 'missing_objection_handling' in score['risk_flags']:
            actions.append('Work on addressing objections such as budget or timeline concerns.')
        if 'pricing_risk' in score['risk_flags']:
            actions.append('Avoid making guarantees or promises about ROI. Use safe pricing language.')
        if 'missing_next_step' in score['risk_flags']:
            actions.append('Always define a clear next step, such as scheduling a follow-up or sending a proposal.')
        if 'missing_compliance' in score['risk_flags']:
            actions.append('Include a compliance disclaimer in your calls.')
    return {'actions': actions}
