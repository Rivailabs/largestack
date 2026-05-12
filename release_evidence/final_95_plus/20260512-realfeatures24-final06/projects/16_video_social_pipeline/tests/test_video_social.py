import pytest
from video_social import make_script, route_model, publish_decision

def test_make_script():
    r = make_script('product short')
    assert r['script'] and len(r['storyboard']) >= 3

def test_route_model():
    assert route_model('instagram reel') == 'mock-video-fast'

def test_publish_decision():
    assert publish_decision()['executed'] is False
