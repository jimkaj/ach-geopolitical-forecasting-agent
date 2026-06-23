"""Tests for the HTML matrix renderer (pure formatting)."""

from datetime import datetime

from agents.base import EvidenceRow, MatrixAgentState
from agents.matrix_agent import compute_scores, rank_by_inconsistency
from tools.matrix_view import (
    _compute_score_series,
    render_matrix_html,
    render_summary_html,
)

NAMES = {"h1": "China supports US", "h2": "China neutral", "h3": "China opposes US"}


def _render(rows, title="ACH Decision Matrix", return_url=""):
    hyp_ids = list(NAMES.keys())
    scores = compute_scores(rows, hyp_ids)
    ranking = rank_by_inconsistency(scores)
    return render_matrix_html(rows, NAMES, scores, ranking, "2026-06-22 12:00:00 UTC",
                              title=title, return_url=return_url)


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


def test_custom_title_appears_in_html():
    rows = [EvidenceRow(article_id="a1", marks={"h1": "+", "h2": "N/A", "h3": "-"})]
    html = _render(rows, title="ACH Decision Matrix — China")
    assert "ACH Decision Matrix — China" in html


def test_return_url_renders_back_button():
    rows = [EvidenceRow(article_id="a1", marks={"h1": "+", "h2": "N/A", "h3": "-"})]
    html = _render(rows, return_url="../summary.html")
    assert "Back to Summary" in html
    assert "../summary.html" in html


def test_no_return_button_when_url_empty():
    rows = [EvidenceRow(article_id="a1", marks={"h1": "+", "h2": "N/A", "h3": "-"})]
    html = _render(rows, return_url="")
    assert "Back to Summary" not in html


# --------------------------------------------------------------------------- #
# _compute_score_series
# --------------------------------------------------------------------------- #
def test_score_series_cumulates_correctly():
    rows = [
        EvidenceRow(article_id="a1", published_date=datetime(2026, 6, 1),
                    marks={"h1": "++", "h2": "N/A", "h3": "N/A"}),  # +2 - 0 = +2
        EvidenceRow(article_id="a2", published_date=datetime(2026, 6, 2),
                    marks={"h1": "N/A", "h2": "N/A", "h3": "++"}),  # 0 - 2 = -2, cumul=0
        EvidenceRow(article_id="a3", published_date=datetime(2026, 6, 3),
                    marks={"h1": "+", "h2": "++", "h3": "-"}),       # 1 - (-1) = +2, cumul=+2
    ]
    series = _compute_score_series(rows, NAMES)
    assert len(series) == 3
    assert series[0] == ["2026-06-01", 2, rows[0].title or rows[0].article_id]
    assert series[1][1] == 0    # cumulative
    assert series[2][1] == 2


def test_score_series_skips_undated_rows():
    rows = [
        EvidenceRow(article_id="dated", published_date=datetime(2026, 6, 1),
                    marks={"h1": "+", "h2": "N/A", "h3": "N/A"}),
        EvidenceRow(article_id="undated", published_date=None,
                    marks={"h1": "++", "h2": "N/A", "h3": "N/A"}),
    ]
    series = _compute_score_series(rows, NAMES)
    assert len(series) == 1
    assert series[0][0] == "2026-06-01"


def test_score_series_sorted_oldest_first():
    rows = [
        EvidenceRow(article_id="new", published_date=datetime(2026, 6, 10),
                    marks={"h1": "+", "h2": "N/A", "h3": "N/A"}),
        EvidenceRow(article_id="old", published_date=datetime(2026, 6, 1),
                    marks={"h1": "+", "h2": "N/A", "h3": "N/A"}),
    ]
    series = _compute_score_series(rows, NAMES)
    assert series[0][0] == "2026-06-01"
    assert series[1][0] == "2026-06-10"


def test_score_series_empty_with_fewer_than_three_hypotheses():
    only_two = {"h1": "Supports", "h2": "Neutral"}
    rows = [EvidenceRow(article_id="a1", published_date=datetime(2026, 6, 1),
                        marks={"h1": "+", "h2": "N/A"})]
    assert _compute_score_series(rows, only_two) == []


def test_h2_neutral_contributes_zero():
    rows = [
        EvidenceRow(article_id="a1", published_date=datetime(2026, 6, 1),
                    marks={"h1": "N/A", "h2": "++", "h3": "N/A"}),  # h2 strong neutral
    ]
    series = _compute_score_series(rows, NAMES)
    assert series[0][1] == 0  # no movement on the axis


# --------------------------------------------------------------------------- #
# render_summary_html
# --------------------------------------------------------------------------- #
def _make_state(nation_id: str, rows: list) -> MatrixAgentState:
    state = MatrixAgentState(
        matrix_version="20260622",
        evidence_rows=rows,
        hypothesis_names=NAMES,
        nation_id=nation_id,
    )
    return state


def test_summary_html_contains_nation_names():
    china_rows = [
        EvidenceRow(article_id="c1", published_date=datetime(2026, 6, 1),
                    marks={"h1": "++", "h2": "N/A", "h3": "-"}),
    ]
    russia_rows = [
        EvidenceRow(article_id="r1", published_date=datetime(2026, 6, 2),
                    marks={"h1": "--", "h2": "N/A", "h3": "++"}),
    ]
    states = {
        "china": _make_state("china", china_rows),
        "russia": _make_state("russia", russia_rows),
    }
    html = render_summary_html(states)
    assert "<!DOCTYPE html>" in html
    assert "China" in html
    assert "Russia" in html


def test_summary_html_contains_navigation_links():
    states = {
        "china": _make_state("china", [
            EvidenceRow(article_id="c1", published_date=datetime(2026, 6, 1),
                        marks={"h1": "+", "h2": "N/A", "h3": "N/A"}),
        ]),
    }
    html = render_summary_html(states)
    assert "china/acch_matrix.html" in html


def test_summary_html_escapes_nation_names():
    states = {
        '<script>': _make_state('<script>', []),
    }
    html = render_summary_html(states)
    assert "<script>" not in html.split("<style>")[0]  # raw tag not in visible content


def test_line_graph_embedded_in_nation_html():
    rows = [
        EvidenceRow(article_id="a1", published_date=datetime(2026, 6, 1),
                    marks={"h1": "++", "h2": "N/A", "h3": "-"}, title="Test article"),
    ]
    html = _render(rows, title="ACH Decision Matrix — China")
    assert "<canvas" in html
    assert "alignChart" in html
    assert "2026-06-01" in html    # date embedded in JS data
