"""Tests for the Guardian-backed WebScraper (no network)."""

from unittest.mock import MagicMock

import pytest

from tools.web_scraper import WebScraper

WHITELIST = {"content.guardianapis.com", "theguardian.com"}


@pytest.fixture
def scraper(config):
    return WebScraper(config, WHITELIST)


# --------------------------------------------------------------------------- #
# _is_domain_allowed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://content.guardianapis.com/search", True),
        ("https://www.theguardian.com/world/x", True),   # www stripped
        ("https://theguardian.com/world/x", True),
        ("https://evil.com/x", False),
        ("https://content.guardianapis.com.evil.com/x", False),  # suffix trick
    ],
)
def test_is_domain_allowed(scraper, url, allowed):
    assert scraper._is_domain_allowed(url) is allowed


# --------------------------------------------------------------------------- #
# _recent_from_date
# --------------------------------------------------------------------------- #
def test_recent_from_date_returns_iso(scraper, config):
    config.guardian_from_days = 7
    out = scraper._recent_from_date()
    assert out is not None and len(out) == 10 and out[4] == "-"  # YYYY-MM-DD


def test_recent_from_date_disabled(scraper, config):
    config.guardian_from_days = 0
    assert scraper._recent_from_date() is None


# --------------------------------------------------------------------------- #
# _parse_guardian_result
# --------------------------------------------------------------------------- #
def test_parse_full_result(scraper):
    result = {
        "id": "world/2026/jun/22/slug",
        "webUrl": "https://www.theguardian.com/world/2026/jun/22/slug",
        "webPublicationDate": "2026-06-22T09:30:00Z",
        "fields": {"headline": "Big headline", "bodyText": "Full body text here."},
    }
    parsed = scraper._parse_guardian_result(result)
    assert parsed["article_id"] == "world/2026/jun/22/slug"
    assert parsed["url"] == result["webUrl"]
    assert parsed["title"] == "Big headline"
    assert parsed["content"] == "Full body text here."
    assert parsed["source"] == "The Guardian"
    assert parsed["published_date"].year == 2026


def test_parse_missing_weburl_returns_none(scraper):
    assert scraper._parse_guardian_result({"id": "x", "fields": {}}) is None


def test_parse_empty_body_falls_back_to_title(scraper):
    result = {
        "id": "x", "webUrl": "https://www.theguardian.com/x",
        "webTitle": "Title only", "fields": {"bodyText": ""},
    }
    parsed = scraper._parse_guardian_result(result)
    assert parsed["content"] == "Title only"


def test_parse_bad_date_is_tolerated(scraper):
    result = {
        "id": "x", "webUrl": "https://www.theguardian.com/x",
        "webPublicationDate": "not-a-date", "fields": {"headline": "h", "bodyText": "b"},
    }
    parsed = scraper._parse_guardian_result(result)
    assert parsed["published_date"] is None


# --------------------------------------------------------------------------- #
# search_articles — mocked fetch
# --------------------------------------------------------------------------- #
def _api_response(results, status="ok"):
    m = MagicMock()
    m.json = lambda: {"response": {"status": status, "total": len(results), "results": results}}
    return m


def _result(i):
    return {
        "id": f"world/2026/jun/22/a{i}",
        "webUrl": f"https://www.theguardian.com/world/2026/jun/22/a{i}",
        "webPublicationDate": "2026-06-22T09:30:00Z",
        "fields": {"headline": f"Headline {i}", "bodyText": f"Body {i}"},
    }


def test_search_articles_parses_results(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_with_retries", lambda url, params=None: _api_response([_result(0), _result(1)]))
    arts = scraper.search_articles("china iran")
    assert len(arts) == 2
    assert arts[0]["title"] == "Headline 0"


def test_search_articles_respects_max(scraper, config, monkeypatch):
    config.scraper_max_articles = 3
    monkeypatch.setattr(
        scraper, "fetch_with_retries", lambda url, params=None: _api_response([_result(i) for i in range(10)])
    )
    assert len(scraper.search_articles("q")) == 3


def test_search_articles_handles_fetch_failure(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_with_retries", lambda url, params=None: None)
    assert scraper.search_articles("q") == []


def test_search_articles_handles_error_status(scraper, monkeypatch):
    monkeypatch.setattr(
        scraper, "fetch_with_retries", lambda url, params=None: _api_response([], status="error")
    )
    assert scraper.search_articles("q") == []


def test_search_articles_passes_api_key_in_params_not_url(scraper, config, monkeypatch):
    config.guardian_api_key = "SECRET"
    captured = {}

    def fake_fetch(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _api_response([_result(0)])

    monkeypatch.setattr(scraper, "fetch_with_retries", fake_fetch)
    scraper.search_articles("q")
    assert "SECRET" not in captured["url"]          # key not in URL (won't be logged)
    assert captured["params"]["api-key"] == "SECRET"


# --------------------------------------------------------------------------- #
# fetch_article_by_id — mocked fetch
# --------------------------------------------------------------------------- #
def _item_response(item, status="ok"):
    m = MagicMock()
    m.json = lambda: {"response": {"status": status, "content": item}}
    return m


def test_fetch_article_by_id_builds_item_url(scraper, monkeypatch):
    captured = {}

    def fake_fetch(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return _item_response(_result(0))

    monkeypatch.setattr(scraper, "fetch_with_retries", fake_fetch)
    scraper.fetch_article_by_id("world/2026/jun/22/a0")
    assert captured["url"] == "https://content.guardianapis.com/world/2026/jun/22/a0"
    assert captured["params"]["api-key"] == scraper.config.guardian_api_key


def test_fetch_article_by_id_parses_result(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_with_retries", lambda url, params=None: _item_response(_result(0)))
    parsed = scraper.fetch_article_by_id("world/2026/jun/22/a0")
    assert parsed["title"] == "Headline 0"
    assert parsed["content"] == "Body 0"


def test_fetch_article_by_id_handles_fetch_failure(scraper, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_with_retries", lambda url, params=None: None)
    assert scraper.fetch_article_by_id("world/2026/jun/22/a0") is None


def test_fetch_article_by_id_handles_error_status(scraper, monkeypatch):
    monkeypatch.setattr(
        scraper, "fetch_with_retries", lambda url, params=None: _item_response({}, status="error")
    )
    assert scraper.fetch_article_by_id("world/2026/jun/22/a0") is None


# --------------------------------------------------------------------------- #
# fetch_with_retries — whitelist gate + retry/backoff (mocked session + sleep)
# --------------------------------------------------------------------------- #
def test_fetch_rejects_non_whitelisted_domain(scraper):
    assert scraper.fetch_with_retries("https://evil.com/x") is None


def test_fetch_retries_then_succeeds(scraper, monkeypatch):
    import requests

    calls = {"n": 0}

    def flaky_get(url, params=None, timeout=None, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ConnectionError("boom")
        m = MagicMock()
        m.raise_for_status = lambda: None
        return m

    monkeypatch.setattr(scraper.session, "get", flaky_get)
    monkeypatch.setattr("tools.web_scraper.time.sleep", lambda *_: None)
    resp = scraper.fetch_with_retries("https://content.guardianapis.com/search", params={"q": "x"})
    assert resp is not None
    assert calls["n"] == 2
