import re

def assess_vendor(vendor):
    reasons = []
    score = 0
    # Security risk
    if not vendor.get('soc2'):
        score += 30
        reasons.append('No SOC2 certification')
    # Privacy risk
    if not vendor.get('dpdp_ready'):
        score += 20
        reasons.append('Not DPDP ready')
    # Country risk
    country = vendor.get('country', '').upper()
    if country not in ('US', 'CA', 'GB', 'AU', 'DE', 'FR'):
        score += 15
        reasons.append('High risk country')
    # Criticality
    criticality = vendor.get('criticality', 'low')
    if criticality == 'high':
        score += 20
        reasons.append('High criticality vendor')
    elif criticality == 'medium':
        score += 10
        reasons.append('Medium criticality vendor')
    # Financial score
    fin = vendor.get('financial_score', 100)
    if fin < 50:
        score += 15
        reasons.append('Low financial score')
    elif fin < 70:
        score += 5
        reasons.append('Moderate financial score')
    # Determine risk level
    if score >= 50:
        risk_level = 'high'
    elif score >= 30:
        risk_level = 'medium'
    else:
        risk_level = 'low'
    return {'risk_level': risk_level, 'score': score, 'reasons': reasons}

def approval_requirements(risk):
    if risk['risk_level'] == 'high':
        return {'approval_required': True, 'executed': False}
    else:
        return {'approval_required': False, 'executed': False}

def policy_answer(question, docs):
    question_lower = question.lower()
    best_answer = None
    best_citations = []
    for doc_name, content in docs.items():
        content_lower = content.lower()
        # Simple keyword matching
        keywords = re.findall(r'\w+', question_lower)
        match_count = sum(1 for kw in keywords if kw in content_lower)
        if match_count > 0:
            # Extract relevant sentence
            sentences = re.split(r'(?<=[.!?])\s+', content)
            for sentence in sentences:
                if any(kw in sentence.lower() for kw in keywords):
                    best_answer = sentence
                    best_citations.append(doc_name)
                    break
    if best_answer:
        return {'answer': best_answer, 'citations': best_citations}
    else:
        return {'answer': 'insufficient evidence', 'citations': []}
