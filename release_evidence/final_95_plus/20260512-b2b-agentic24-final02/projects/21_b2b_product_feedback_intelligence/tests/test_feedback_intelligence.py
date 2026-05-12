import sys
sys.path.insert(0, '.')
from feedback_intelligence import cluster_feedback, roadmap_signals

def test_cluster_feedback():
    items = [
        {'text': 'Need SSO for enterprise deal', 'arr': 100000},
        {'text': 'SSO setup is confusing', 'arr': 50000},
        {'text': 'Dark mode please', 'arr': 1000}
    ]
    clusters = cluster_feedback(items)
    assert 'sso' in clusters
    assert clusters['sso']['count'] == 2
    assert clusters['sso']['arr'] == 150000
    assert 'dark_mode' in clusters
    assert clusters['dark_mode']['count'] == 1

def test_roadmap_signals():
    items = [
        {'text': 'Need SSO for enterprise deal', 'arr': 100000},
        {'text': 'SSO setup is confusing', 'arr': 50000},
        {'text': 'Dark mode please', 'arr': 1000}
    ]
    clusters = cluster_feedback(items)
    signals = roadmap_signals(clusters)
    assert signals[0]['theme'] == 'sso'
    assert signals[0]['priority'] in {'high', 'critical'}
    assert signals[0]['arr'] == 150000
