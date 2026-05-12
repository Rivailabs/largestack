import pytest

from largestack._a2a import _require_http_url as a2a_require_http_url
from largestack._eval.alerts import _require_http_url as alerts_require_http_url


@pytest.mark.parametrize("url", ["https://example.com/hook", "http://localhost:8080/api"])
def test_a2a_allows_http_https(url):
    assert a2a_require_http_url(url) == url


@pytest.mark.parametrize("url", ["file:///etc/passwd", "/tmp/file", "ftp://example.com/x", "javascript:alert(1)", ""])
def test_a2a_rejects_non_http_urls(url):
    with pytest.raises(ValueError):
        a2a_require_http_url(url)


@pytest.mark.parametrize("url", ["https://example.com/hook", "http://localhost:8080/api"])
def test_alerts_allows_http_https(url):
    assert alerts_require_http_url(url) == url


@pytest.mark.parametrize("url", ["file:///etc/passwd", "/tmp/file", "ftp://example.com/x", "javascript:alert(1)", ""])
def test_alerts_rejects_non_http_urls(url):
    with pytest.raises(ValueError):
        alerts_require_http_url(url)
