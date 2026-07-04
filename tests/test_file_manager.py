"""Tests for FileManager: processed-URL persistence."""

from tools.file_manager import FileManager


def test_processed_urls_round_trip(config):
    fm = FileManager(config)
    assert fm.load_processed_urls() == set()

    fm.record_processed_url("https://a.com/1", "id1")
    fm.record_processed_url("https://a.com/2", "id2")

    # A fresh FileManager (new "process") must see the persisted URLs.
    assert FileManager(config).load_processed_urls() == {"https://a.com/1", "https://a.com/2"}


def test_creates_processed_urls_file_with_header(config):
    fm = FileManager(config)
    assert fm.processed_urls_file.exists()
    assert fm.processed_urls_file.read_text().splitlines()[0] == "url,article_id,processed_date"
