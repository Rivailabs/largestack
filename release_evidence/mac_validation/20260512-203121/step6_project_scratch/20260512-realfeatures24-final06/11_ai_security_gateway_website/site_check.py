from pathlib import Path

def check_site():
    html = Path('index.html').read_text().lower()
    checks = {
        'ai security gateway': 'ai security gateway' in html,
        'hero': 'hero' in html,
        'trust': 'trust' in html,
        'request demo': 'request demo' in html
    }
    return checks

if __name__ == '__main__':
    result = check_site()
    for key, value in result.items():
        print(f'{key}: {"PASS" if value else "FAIL"}')
    assert all(result.values()), 'Site check failed'