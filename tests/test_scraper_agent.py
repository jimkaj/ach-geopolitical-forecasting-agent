"""Tests for the ScraperAgent: dedup across runs, ArticleData build, error handling."""

import types

from agents.scraper_agent import ScraperAgent
from tools.file_manager import FileManager


def _raw(i, **overrides):
    d = {
        "article_id": f"world/2026/jun/22/a{i}",
        "title": f"Headline {i}",
        "url": f"https://www.theguardian.com/world/2026/jun/22/a{i}",
        "content": f"Body {i}",
        "published_date": None,
        "source": "The Guardian",
    }
    d.update(overrides)
    return d


def _fake_scraper(raw_list):
    return types.SimpleNamespace(search_articles=lambda q: raw_list)


def test_returns_articledata_objects(config):
    fm = FileManager(config)
    agent = ScraperAgent(config, _fake_scraper([_raw(0), _raw(1)]), fm)
    arts = agent.execute("china iran")
    assert len(arts) == 2
    assert arts[0].article_id == "world/2026/jun/22/a0"
    assert arts[0].source == "The Guardian"


def test_dedup_across_runs(config):
    fm = FileManager(config)
    raw = [_raw(0), _raw(1)]

    first = ScraperAgent(config, _fake_scraper(raw), fm).execute("q")
    assert len(first) == 2

    # Second run, same URLs already persisted -> nothing new.
    second = ScraperAgent(config, _fake_scraper(raw), fm).execute("q")
    assert second == []

    # A new article appears -> only that one comes back.
    third = ScraperAgent(config, _fake_scraper(raw + [_raw(2)]), fm).execute("q")
    assert len(third) == 1
    assert third[0].article_id == "world/2026/jun/22/a2"


def test_processed_urls_are_recorded(config):
    fm = FileManager(config)
    ScraperAgent(config, _fake_scraper([_raw(0), _raw(1)]), fm).execute("q")
    assert fm.load_processed_urls() == {
        "https://www.theguardian.com/world/2026/jun/22/a0",
        "https://www.theguardian.com/world/2026/jun/22/a1",
    }


def test_malformed_item_is_skipped_not_fatal(config):
    fm = FileManager(config)
    # Second item is missing the required 'title' -> ArticleData validation fails.
    bad = {"article_id": "x", "url": "https://www.theguardian.com/x", "content": "c"}
    agent = ScraperAgent(config, _fake_scraper([_raw(0), bad]), fm)
    arts = agent.execute("q")
    assert len(arts) == 1  # good one survives, bad one skipped
    assert arts[0].article_id == "world/2026/jun/22/a0"
