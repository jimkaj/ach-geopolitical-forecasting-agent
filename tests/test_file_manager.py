"""Tests for FileManager: processed-URL persistence, sizing, snapshot pruning."""

import os
import time

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


def test_get_directory_size_mb(config):
    fm = FileManager(config)
    (fm.matrix_dir / "f.txt").write_bytes(b"x" * 1024)
    size = fm.get_directory_size_mb(fm.matrix_dir)
    assert size > 0


def _make_snapshots(fm, n):
    """Create n snapshot files with staggered mtimes (oldest first)."""
    paths = []
    for i in range(n):
        p = fm.matrix_dir / f"acch_matrix_v2026010{i}_000000_000000.csv"
        p.write_bytes(b"x" * 50_000)
        os.utime(p, (time.time() + i, time.time() + i))
        paths.append(p)
    return paths


def test_cleanup_prunes_oldest_first(config):
    fm = FileManager(config)
    _make_snapshots(fm, 5)  # ~250 KB total
    # Cap ~120 KB -> must delete the two oldest to get under.
    fm.cleanup_old_snapshots(max_size_gb=120_000 / (1024**3))

    remaining = sorted(p.name for p in fm.matrix_dir.glob("acch_matrix_v*.csv"))
    assert len(remaining) < 5
    # The newest must survive; the oldest must be gone.
    assert "acch_matrix_v20260104_000000_000000.csv" in remaining
    assert "acch_matrix_v20260100_000000_000000.csv" not in remaining


def test_cleanup_noop_when_under_cap(config):
    fm = FileManager(config)
    _make_snapshots(fm, 3)
    fm.cleanup_old_snapshots(max_size_gb=1.0)  # generous
    assert len(list(fm.matrix_dir.glob("*.csv"))) == 3


def test_cleanup_does_not_crash_stat_after_unlink(config):
    """Regression: cleanup used to stat() a file after unlink() -> FileNotFoundError."""
    fm = FileManager(config)
    _make_snapshots(fm, 4)
    # Tiny cap forces deleting (nearly) everything; must not raise.
    fm.cleanup_old_snapshots(max_size_gb=1e-9)
