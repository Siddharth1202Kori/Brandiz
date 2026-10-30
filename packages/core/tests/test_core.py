import unicodedata

import pytest

from seomaster_core import timing
from seomaster_core.config import Settings
from seomaster_core.domains import InvalidDomainError, normalize_domain
from seomaster_core.markets import Market


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("HTTPS://WWW.Example.com:443/path?x=1", "example.com"),
        ("http://user:pw@shop.example.co.in/", "shop.example.co.in"),
        ("  www.example.com.  ", "example.com"),
        ("bücher.de", "xn--bcher-kva.de"),
    ],
)
def test_normalize_domain(raw: str, expected: str) -> None:
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize(
    "raw", ["", "localhost", "http://127.0.0.1", "foo", "-bad-.com", "site.local", "a..com"]
)
def test_normalize_domain_rejects(raw: str) -> None:
    with pytest.raises(InvalidDomainError):
        normalize_domain(raw)


def test_market_codes() -> None:
    assert Market.IN.location_code == 2356
    assert Market.US.location_code == 2840
    assert Market("in") is Market.IN


def test_settings_accept_short_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("Client_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setenv("Client_Secret", "shh")
    monkeypatch.setenv("SerpApi", "key123")
    s = Settings(_env_file=None)
    assert s.google_client_id == "abc.apps.googleusercontent.com"
    assert s.google_client_secret.get_secret_value() == "shh"
    assert s.serp_api_key.get_secret_value() == "key123"
    assert s.google_oauth_enabled


def test_prod_rejects_dev_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    with pytest.raises(ValueError, match="AUTH_SECRET"):
        Settings(_env_file=None)


def test_server_timing_header() -> None:
    timing.start()
    timing.record("db", 2.0)
    timing.record("db", 1.5)
    timing.record("cache", 0.25)
    assert timing.header_value(10.0) == "db;dur=3.5, cache;dur=0.2, total;dur=10.0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  SEO   Tools ", "seo tools"),
        ("Café́", "café́"),  # NFC keeps combining sequence normalized
        ("Café", "café"),
        ("SEO\tTOOLS\nindia", "seo tools india"),
        ("सर्वश्रेष्ठ SEO", "सर्वश्रेष्ठ seo"),
    ],
)
def test_normalize_keyword(raw: str, expected: str) -> None:
    from seomaster_core.keywords import normalize_keyword

    assert normalize_keyword(raw) == unicodedata.normalize("NFC", expected)


@pytest.mark.parametrize("raw", ["", "   ", "x" * 201])
def test_normalize_keyword_rejects(raw: str) -> None:
    from seomaster_core.keywords import InvalidKeywordError, normalize_keyword

    with pytest.raises(InvalidKeywordError):
        normalize_keyword(raw)
