import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from hal_mosaic import classify_ticket, route_ticket, sla_minutes

def test_classify_ticket_mosaic_avionics():
    c = classify_ticket('MOSAIC avionics safety production write')
    assert c['domain'] == 'mosaic_avionics'

def test_route_ticket_mosaic_avionics():
    c = classify_ticket('MOSAIC avionics safety production write')
    r = route_ticket(c)
    assert r['approval_required'] is True

def test_sla_minutes_mosaic_avionics():
    c = classify_ticket('MOSAIC avionics safety production write')
    assert sla_minutes(c) <= 240

def test_classify_ticket_general():
    c = classify_ticket('Some random issue')
    assert c['domain'] == 'general'

def test_route_ticket_general():
    c = classify_ticket('Some random issue')
    r = route_ticket(c)
    assert r['approval_required'] is False

def test_sla_minutes_general():
    c = classify_ticket('Some random issue')
    assert sla_minutes(c) == 480
