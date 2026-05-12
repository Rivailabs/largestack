import re

def extract_obligations(text: str) -> dict:
    obligations = {}
    # auto-renewal
    if re.search(r'auto.renew', text, re.IGNORECASE):
        obligations['auto_renewal'] = True
    else:
        obligations['auto_renewal'] = False
    # payment terms
    m = re.search(r'payment terms?\s*(.*?)(?:\.|$)', text, re.IGNORECASE)
    if m:
        obligations['payment_terms'] = m.group(1).strip()
    else:
        obligations['payment_terms'] = None
    return obligations

def flag_contract_risks(text: str) -> list:
    risks = []
    # liability cap absence: negative phrases indicate missing control
    if re.search(r'no liability cap|without liability cap|liability cap absent', text, re.IGNORECASE):
        risks.append('missing_liability_cap')
    # DPA absence
    if re.search(r'dpa not attached|no dpa|dpa absent', text, re.IGNORECASE):
        risks.append('missing_dpa')
    # non-standard governing law (not Earth/standard)
    if re.search(r'governing law\s*(.*?)(?:\.|$)', text, re.IGNORECASE):
        law_match = re.search(r'governing law\s*(.*?)(?:\.|$)', text, re.IGNORECASE)
        law = law_match.group(1).strip().lower()
        if law not in ('', 'earth', 'standard', 'delaware', 'new york', 'california', 'england', 'uk'):
            risks.append('non_standard_governing_law')
    return risks

def approval_route(risks: list) -> dict:
    if risks:
        return {'approval_required': True, 'executed': False}
    else:
        return {'approval_required': False, 'executed': True}
