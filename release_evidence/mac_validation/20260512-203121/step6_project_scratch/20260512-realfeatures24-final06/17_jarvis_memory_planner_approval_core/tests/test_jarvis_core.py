from jarvis_core import JarvisCore

def test_remember_recall():
    j = JarvisCore(':memory:')
    j.remember('prefs', {'focus': 'maker'})
    assert j.recall('prefs')['focus'] == 'maker'

def test_plan_day():
    j = JarvisCore(':memory:')
    plans = j.plan_day(['code'])
    assert len(plans) == 1
    assert plans[0]['task'] == 'code'

def test_decide_action_risky():
    j = JarvisCore(':memory:')
    result = j.decide_action('send_email', {'to': 'x@example.com'})
    assert result['executed'] is False

def test_decide_action_safe():
    j = JarvisCore(':memory:')
    result = j.decide_action('read_file', {'path': '/tmp/test.txt'})
    assert result['executed'] is True
