import pytest
from code_reviewer import find_issues, suggest_patch


def test_find_issues_hardcoded_secret():
    source = '''
CONFIG_VALUE = "demo_insecure_value"
API_KEY = "demo_key"
'''
    issues = find_issues(source)
    assert 'hardcoded_secret' in issues
    assert issues['hardcoded_secret'] == [2, 3]


def test_find_issues_sql_fstring():
    source = '''
query = f"SELECT * FROM users WHERE id = {user_id}"
'''
    issues = find_issues(source)
    assert 'sql_string_formatting' in issues
    assert issues['sql_string_formatting'] == [2]


def test_find_issues_sql_percent():
    source = '''
query = "SELECT * FROM users WHERE id = %s" % user_id
'''
    issues = find_issues(source)
    assert 'sql_string_formatting' in issues
    assert issues['sql_string_formatting'] == [2]


def test_find_issues_sql_format():
    source = '''
query = "SELECT * FROM users WHERE id = {}".format(user_id)
'''
    issues = find_issues(source)
    assert 'sql_string_formatting' in issues
    assert issues['sql_string_formatting'] == [2]


def test_find_issues_sql_concat():
    source = '''
query = "SELECT * FROM users WHERE id = " + user_id
'''
    issues = find_issues(source)
    assert 'sql_string_formatting' in issues
    assert issues['sql_string_formatting'] == [2]


def test_suggest_patch():
    source = '''API_KEY = "demo_key"'''
    patched = suggest_patch(source)
    assert 'os.environ.get' in patched
    assert 'demo_key' not in patched


def test_suggest_patch_no_issue():
    source = '''x = 5'''
    patched = suggest_patch(source)
    assert patched == source


def test_suggest_patch_multiple():
    source = '''API_KEY = "demo_key"
OTHER_SECRET = "demo_secret"'''
    patched = suggest_patch(source)
    assert 'os.environ.get' in patched
    assert 'demo_key' not in patched
    assert 'demo_secret' not in patched


def test_suggest_patch_import_already_present():
    source = '''import os
API_KEY = "demo_key"'''
    patched = suggest_patch(source)
    assert 'os.environ.get' in patched
    assert 'demo_key' not in patched


def test_find_issues_membership():
    source = '''
CONFIG_VALUE = "demo_insecure_value"
query = f"SELECT * FROM users WHERE id = {user_id}"
'''
    issues = find_issues(source)
    assert 'hardcoded_secret' in issues
    assert 'sql_string_formatting' in issues


def test_find_issues_no_issues():
    source = '''x = 5'''
    issues = find_issues(source)
    assert issues == {}
