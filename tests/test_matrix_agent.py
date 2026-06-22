"""Tests for the MatrixAgent: evidence-row model, inconsistency scoring,
cross-run accumulation, diagnosticity, and output artifacts."""

import json
from datetime import datetime

from agents.matrix_agent import (
    MatrixAgent,
    compute_scores,
    rank_by_inconsistency,
)
from tools.file_manager import FileManager


# --------------------------------------------------------------------------- #
# Scoring (pure functions)
# --------------------------------------------------------------------------- #
def test_compute_scores_counts_and_weights():
    from agents.base import EvidenceRow

    rows = [
        EvidenceRow(article_id="a1", marks={"h1": "++", "h2": "--", "h3": "N/A"}),
        EvidenceRow(article_id="a2", marks={"h1": "+", "h2": "-", "h3": "N/A"}),
    ]
    scores = compute_scores(rows, ["h1", "h2", "h3"])
    assert scores["h1"]["inconsistency"] == 0.0   # ++, + -> no evidence against
    assert scores["h1"]["support"] == 3.0          # 2 + 1
    assert scores["h2"]["inconsistency"] == 3.0    # -- (2) + - (1)
    assert scores["h3"]["na"] == 2


def test_rank_lowest_inconsistency_first():
    from agents.base import EvidenceRow

    rows = [
        EvidenceRow(article_id="a1", marks={"h1": "++", "h2": "--", "h3": "-"}),
        EvidenceRow(article_id="a2", marks={"h1": "+", "h2": "-", "h3": "N/A"}),
    ]
    scores = compute_scores(rows, ["h1", "h2", "h3"])
    ranking = rank_by_inconsistency(scores)
    assert ranking[0] == "h1"   # zero evidence against -> most likely
    assert ranking[-1] == "h2"  # most evidence against -> least likely


# --------------------------------------------------------------------------- #
# Ingestion + state
# --------------------------------------------------------------------------- #
def test_ingest_builds_evidence_rows(config, assessment_factory):
    agent = MatrixAgent(config, FileManager(config))
    state = agent.execute([
        assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"}, confidence=0.9),
        assessment_factory("a2", {"h1": "+", "h2": "N/A", "h3": "--"}),
    ])
    assert state.article_count == 2
    row = next(r for r in state.evidence_rows if r.article_id == "a1")
    assert row.marks == {"h1": "++", "h2": "N/A", "h3": "-"}
    assert row.confidence == 0.9
    assert state.hypothesis_names == {"h1": "Hypothesis h1", "h2": "Hypothesis h2", "h3": "Hypothesis h3"}


def test_diagnosticity():
    from agents.base import EvidenceRow

    assert EvidenceRow(article_id="x", marks={"h1": "++", "h2": "-", "h3": "N/A"}).is_diagnostic
    # all the same mark -> consistent with everything -> not diagnostic
    assert not EvidenceRow(article_id="y", marks={"h1": "N/A", "h2": "N/A", "h3": "N/A"}).is_diagnostic


def test_accumulation_across_runs(config, assessment_factory):
    fm = FileManager(config)
    MatrixAgent(config, fm).execute([
        assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"}),
        assessment_factory("a2", {"h1": "+", "h2": "N/A", "h3": "--"}),
    ])

    # New agent must load prior rows from JSON state, then add to them.
    agent2 = MatrixAgent(config, fm)
    assert agent2.state.article_count == 2
    state = agent2.execute([assessment_factory("a3", {"h1": "++", "h2": "N/A", "h3": "N/A"})])
    assert state.article_count == 3
    assert {r.article_id for r in state.evidence_rows} == {"a1", "a2", "a3"}


def test_reingesting_same_article_replaces_row(config, assessment_factory):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    agent.execute([assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "N/A"})])
    state = agent.execute([assessment_factory("a1", {"h1": "--", "h2": "N/A", "h3": "N/A"})])
    assert state.article_count == 1  # replaced, not duplicated
    assert state.evidence_rows[0].marks["h1"] == "--"


def test_rows_sorted_most_recent_first(config, assessment_factory):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    agent.execute([
        assessment_factory("old", {"h1": "N/A"}, published_date=datetime(2026, 1, 1)),
        assessment_factory("new", {"h1": "N/A"}, published_date=datetime(2026, 6, 1)),
    ])
    ordered = agent._sorted_rows()
    assert ordered[0].article_id == "new"
    assert ordered[1].article_id == "old"


# --------------------------------------------------------------------------- #
# Output artifacts
# --------------------------------------------------------------------------- #
def test_writes_state_json_and_html(config, assessment_factory):
    agent = MatrixAgent(config, FileManager(config))
    agent.execute([assessment_factory("a1", {"h1": "++", "h2": "N/A", "h3": "-"})])

    assert (agent.matrix_dir / "matrix_state.json").exists()
    assert (agent.matrix_dir / "acch_matrix.html").exists()
    assert list(agent.matrix_dir.glob("acch_matrix_v*.html"))  # versioned snapshot

    state_doc = json.loads((agent.matrix_dir / "matrix_state.json").read_text(encoding="utf-8"))
    assert state_doc["evidence_rows"][0]["article_id"] == "a1"
    html = (agent.matrix_dir / "acch_matrix.html").read_text(encoding="utf-8")
    assert "ACH Decision Matrix" in html


def test_execute_invokes_cleanup(config, assessment_factory, monkeypatch):
    fm = FileManager(config)
    agent = MatrixAgent(config, fm)
    called = {"n": 0}
    monkeypatch.setattr(fm, "cleanup_old_snapshots", lambda cap: called.__setitem__("n", called["n"] + 1))
    agent.execute([assessment_factory("a1", {"h1": "N/A", "h2": "N/A", "h3": "N/A"})])
    assert called["n"] == 1


def test_fresh_when_no_state(config):
    agent = MatrixAgent(config, FileManager(config))
    assert agent.state.article_count == 0
    assert agent.state.evidence_rows == []
