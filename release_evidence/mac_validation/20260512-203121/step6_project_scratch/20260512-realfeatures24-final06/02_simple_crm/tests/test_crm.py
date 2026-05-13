import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from crm import create_contact, list_contacts, update_stage, score_lead


@pytest.fixture(autouse=True)
def clear_data():
    # Clear contacts before each test
    data_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'contacts.json')
    if os.path.exists(data_file):
        os.remove(data_file)
    yield
    if os.path.exists(data_file):
        os.remove(data_file)


def test_public_contract():
    c = create_contact('a@example.com', 'A', stage='lead')
    create_contact('a@example.com', 'A2', stage='prospect')
    assert len(list_contacts()) == 1
    assert update_stage(c['id'], 'customer')['stage'] == 'customer'
    assert 0 <= score_lead(c) <= 100


def test_create_contact():
    c = create_contact('test@example.com', 'Test User')
    assert c['email'] == 'test@example.com'
    assert c['name'] == 'Test User'
    assert c['stage'] == 'lead'


def test_duplicate_email_updates():
    c1 = create_contact('dup@example.com', 'Original')
    c2 = create_contact('dup@example.com', 'Updated')
    assert c1['id'] == c2['id']
    assert c2['name'] == 'Updated'


def test_list_contacts():
    create_contact('a@example.com', 'A')
    create_contact('b@example.com', 'B')
    contacts = list_contacts()
    assert len(contacts) == 2


def test_update_stage():
    c = create_contact('c@example.com', 'C')
    updated = update_stage(c['id'], 'customer')
    assert updated['stage'] == 'customer'


def test_score_lead():
    c = create_contact('d@example.com', 'David')
    score = score_lead(c)
    assert 0 <= score <= 100
