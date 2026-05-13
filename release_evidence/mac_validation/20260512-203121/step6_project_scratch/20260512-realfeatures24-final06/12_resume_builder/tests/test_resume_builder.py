from resume_builder import build_resume

def test_build_resume_contains_required_skills():
    md, meta = build_resume({'name': 'A', 'role': 'data analyst'})
    assert 'SQL' in md
    assert 'Excel' in md
    assert 'fabricate' in md.lower()
    assert meta['ats_score'] > 0

def test_build_resume_metadata():
    md, meta = build_resume({'name': 'Bob', 'role': 'data analyst'})
    assert 'Bob' in md
    assert meta['experience_count'] == 2
    assert meta['ats_score'] > 0

def test_build_resume_defaults():
    md, meta = build_resume({})
    assert 'Unknown' in md
    assert 'data analyst' in md
    assert meta['ats_score'] > 0
