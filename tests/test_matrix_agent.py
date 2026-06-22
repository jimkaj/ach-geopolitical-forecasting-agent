"""Tests for the MatrixAgent: tallying, net support, cross-run accumulation, cleanup."""

import csv

from agents.matrix_agent import MatrixAgent
from tools.file_manager import FileManager


def test_ingest_tallies_and_net_support(config, assessment_factory):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    state = agent.execute([
        assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"}),
        assessment_factory("a2", {"h1": "+", "h2": "N/A", "h3": "--"}),
    ])
    h1 = state.hypothesis_aggregates["h1"]
    assert h1.evidence_tally == {"++": 1, "+": 1, "N/A": 0, "-": 0, "--": 0}
    assert h1.net_support == 3.0          # 2 + 1
    assert state.hypothesis_aggregates["h2"].net_support == 0.0   # N/A x2
    assert state.hypothesis_aggregates["h3"].net_support == -3.0  # -1 + -2
    assert state.article_count == 2


def test_snapshot_written_with_id_column(config, assessment_factory):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    agent.execute([assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"})])

    snaps = list(agent.matrix_dir.glob("acch_matrix_v*.csv"))
    assert len(snaps) == 1
    with open(snaps[0], encoding="utf-8") as f:
        header = next(csv.reader(f))
    assert header[0] == "hypothesis_id"


def test_accumulation_across_runs(config, assessment_factory):
    fm = FileManager(config)

    # Run 1
    MatrixAgent(config, fm).execute([
        assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"}),
        assessment_factory("a2", {"h1": "+", "h2": "N/A", "h3": "--"}),
    ])

    # Run 2: a brand-new agent must LOAD the prior snapshot, then add to it.
    agent2 = MatrixAgent(config, fm)
    assert agent2.state.article_count == 2  # carried over
    assert agent2.state.hypothesis_aggregates["h1"].evidence_tally["++"] == 1

    state = agent2.execute([assessment_factory("a3", {"h1": "++", "h2": "N/A", "h3": "N/A"})])
    assert state.article_count == 3
    assert state.hypothesis_aggregates["h1"].evidence_tally == {
        "++": 2, "+": 1, "N/A": 0, "-": 0, "--": 0,
    }
    assert state.hypothesis_aggregates["h1"].net_support == 5.0


def test_fresh_when_no_snapshot(config):
    agent = MatrixAgent(config, FileManager(config))
    assert agent.state.article_count == 0
    assert agent.state.hypothesis_aggregates == {}


def test_legacy_snapshot_without_id_column_starts_fresh(config):
    fm = FileManager(config)
    # Write an old-format snapshot (no hypothesis_id column).
    legacy = fm.matrix_dir / "acch_matrix_v20250101_000000_000000.csv"
    legacy.write_text(
        "Hypothesis,++,+,N/A,-,--,Net Support\nChina supports US,5,0,0,0,0,10\n",
        encoding="utf-8",
    )
    agent = MatrixAgent(config, fm)
    assert agent.state.article_count == 0  # refused to load lossy legacy format


def test_execute_invokes_cleanup(config, assessment_factory, monkeypatch):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    called = {"n": 0}
    monkeypatch.setattr(
        fm, "cleanup_old_snapshots", lambda cap: called.__setitem__("n", called["n"] + 1)
    )
    agent.execute([assessment_factory("a1", {"h1": "N/A", "h2": "N/A", "h3": "N/A"})])
    assert called["n"] == 1
