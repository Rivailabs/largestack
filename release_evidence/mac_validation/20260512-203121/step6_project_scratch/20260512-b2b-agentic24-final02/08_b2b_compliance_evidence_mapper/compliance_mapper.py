import re

def map_control_to_evidence(controls, evidence):
    mapping = {}
    for ctrl in controls:
        cid = ctrl['id']
        text = ctrl['text']
        keywords = set(re.findall(r'[a-zA-Z]+', text.lower()))
        matched = []
        for fname, ftext in evidence.items():
            ftext_lower = ftext.lower()
            if any(kw in ftext_lower for kw in keywords):
                matched.append(fname)
        if matched:
            mapping[cid] = {'status': 'mapped', 'evidence': matched}
        else:
            mapping[cid] = {'status': 'missing', 'evidence': []}
    return mapping

def gap_report(mapping):
    missing = [cid for cid, info in mapping.items() if info['status'] == 'missing']
    actions = []
    for cid in missing:
        actions.append({
            'control_id': cid,
            'remediation': 'Implement evidence collection for control ' + cid,
            'owner': 'compliance_team'
        })
    return {'missing_count': len(missing), 'actions': actions}
