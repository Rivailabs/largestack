from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from site_check import check_site

def test_site_check():
    result = check_site()
    assert result['ai security gateway'] == True
    assert result['hero'] == True
    assert result['trust'] == True
    assert result['request demo'] == True

def test_index_html_contains_required():
    html = Path('index.html').read_text().lower()
    assert 'ai security gateway' in html
    assert 'hero' in html
    assert 'trust' in html
    assert 'request demo' in html