"""Tests for the HTML matrix renderer (pure formatting)."""

from datetime import datetime

from agents.base import EvidenceRow
from agents.matrix_agent import compute_scores, rank_by_inconsistency
from tools.matrix_view import render_matrix_html

NAMES = {"h1": "China supports US", "h2": "China neutral", "h3": "China supports Iran"}


def _render(rows):
    hyp_ids = list(NAMES.keys())
    scores = compute_scores(rows, hyp_ids)
    ranking = rank_by_inconsistency(scores)
    return render_matrix_html(rows, NAMES, scores, ranking, "2026-06-22 12:00:00 UTC")


def test_renders_marks_and_hypotheses():
    rows = [
        EvidenceRow(
            article_id="a1", title="Test headline", source="The Guardian",
            published_date=datetime(2026, 6, 22),
            marks={"h1": "++", "h2": "N/A", "h3": "--"}, confidence=0.83,
        )
    ]
    html = _render(rows)
    assert "<!DOCTYPE html>" in html
    assert "China supports US" in html
    assert "Test headline" in html
    assert "2026-06-22" in html
    assert "83%" in html            # confidence column
    assert "++" in html and "--" in html


def test_escapes_html_in_titles():
    rows = [EvidenceRow(article_id="a1", title="<script>alert(1)</script>",
                        marks={"h1": "N/A", "h2": "N/A", "h3": "N/A"})]
    html = _render(rows)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_empty_matrix_renders_placeholder():
    html = render_matrix_html([], NAMES, compute_scores([], list(NAMES)), [], "now")
    assert "No evidence rows yet" in html or "No hypotheses" in html


def test_ranking_reflects_inconsistency():
    rows = [EvidenceRow(article_id="a1", marks={"h1": "++", "h2": "--", "h3": "-"})]
    html = _render(rows)
    # h2 has the most evidence against -> should not be the lead; h1 leads.
    assert "Current lead: <b>China supports US</b>" in html
