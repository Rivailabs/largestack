import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from code_reviewer import find_issues, suggest_patch


def test_find_issues_hardcoded_secret():
    source = "PASSWORD = 'changeme'"
    issues = find_issues(source)
    assert 'hardcoded_secret' in issues


def test_find_issues_sql_fstring():
    source = 'query = f"SELECT * FROM users WHERE id = {user_id}"'
    issues = find_issues(source)
    assert 'sql_string_formatting' in issues


def test_find_issues_both():
    source = '''PASSWORD = 'secret'
query = f"SELECT * FROM users WHERE name = {name}"'''
    issues = find_issues(source)
    assert 'hardcoded_secret' in issues
    assert 'sql_string_formatting' in issues


def test_find_issues_no_issues():
    source = "x = 5"
    issues = find_issues(source)
    assert issues == []


def test_suggest_patch_hardcoded_secret():
    source = "PASSWORD = 'changeme'"
    patched = suggest_patch(source)
    assert 'APP_PASSWORD' in patched
    assert 'changeme' not in patched


def test_suggest_patch_sql_fstring():
    source = 'query = f"SELECT * FROM users WHERE id = {user_id}"'
    patched = suggest_patch(source)
    assert '?' in patched
    assert '{user_id}' not in patched


def test_suggest_patch_sql_fstring_multiple():
    source = 'query = f"SELECT * FROM users WHERE id = {user_id} AND name = {name}"'
    patched = suggest_patch(source)
    # Should have two ? placeholders
    assert patched.count('?') == 2


def test_suggest_patch_no_issues():
    source = "x = 5"
    patched = suggest_patch(source)
    assert patched == source
