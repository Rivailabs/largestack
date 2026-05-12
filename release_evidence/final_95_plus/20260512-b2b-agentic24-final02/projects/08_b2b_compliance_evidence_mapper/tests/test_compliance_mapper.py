from compliance_mapper import map_control_to_evidence, gap_report

def test_map_control_to_evidence():
    controls = [
        {'id': 'AC-1', 'text': 'Access reviews must be quarterly'},
        {'id': 'IR-1', 'text': 'Incident response tabletop annually'}
    ]
    evidence = {
        'access_review_q1.pdf': 'Quarterly access review completed',
        'backup.txt': 'Backups tested'
    }
    mapping = map_control_to_evidence(controls, evidence)
    assert mapping['AC-1']['status'] == 'mapped'
    assert mapping['IR-1']['status'] == 'missing'

def test_gap_report():
    controls = [
        {'id': 'AC-1', 'text': 'Access reviews must be quarterly'},
        {'id': 'IR-1', 'text': 'Incident response tabletop annually'}
    ]
    evidence = {
        'access_review_q1.pdf': 'Quarterly access review completed',
        'backup.txt': 'Backups tested'
    }
    mapping = map_control_to_evidence(controls, evidence)
    gap = gap_report(mapping)
    assert gap['missing_count'] == 1
    assert gap['actions'][0]['control_id'] == 'IR-1'
