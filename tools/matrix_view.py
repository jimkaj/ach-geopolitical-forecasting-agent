"""Render the ACH decision matrix as a self-contained, color-coded HTML page.

Layout follows Heuer Chapter 8: evidence (articles) down the rows, hypotheses
across the columns, with a per-hypothesis inconsistency ranking (lowest = most
likely). Pure presentation — no I/O, no domain logic.
"""

from html import escape

# Per-mark cell styling (background, text color, tooltip).
_MARK_STYLE = {
    "++": ("#1b5e20", "#ffffff", "Strong support"),
    "+": ("#66bb6a", "#0b2e13", "Weak support"),
    "N/A": ("#e0e0e0", "#555555", "Not relevant / no evidence"),
    "-": ("#ef9a9a", "#3b0d0d", "Weak evidence against"),
    "--": ("#b71c1c", "#ffffff", "Strong evidence against"),
}

_CSS = """
:root { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; }
body { margin: 24px; color: #1a1a1a; background: #fafafa; }
h1 { font-size: 20px; margin: 0 0 4px; }
.meta { color: #777; font-size: 12px; margin-bottom: 20px; }
.note { color: #555; font-size: 12px; font-style: italic; margin: 6px 0 18px; }
table { border-collapse: collapse; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.12); }
th, td { border: 1px solid #ddd; padding: 6px 9px; font-size: 13px; vertical-align: middle; }
th { background: #f1f3f4; text-align: left; font-weight: 600; }
.rank-table { margin-bottom: 26px; }
.rank-table td.score { text-align: right; font-variant-numeric: tabular-nums; }
.rank-1 { background: #e8f5e9; font-weight: 600; }
.hyp-col { text-align: center; min-width: 64px; }
.hyp-id { color: #888; font-weight: 400; font-size: 11px; }
.mark { text-align: center; font-weight: 700; min-width: 48px; }
.date { white-space: nowrap; color: #444; font-variant-numeric: tabular-nums; }
.article { max-width: 420px; }
.src { color: #888; font-size: 11px; }
.conf-wrap { min-width: 90px; }
.conf-bar { height: 8px; border-radius: 4px; background: #eee; overflow: hidden; }
.conf-fill { height: 100%; }
.conf-pct { font-size: 11px; color: #555; font-variant-numeric: tabular-nums; }
.nondiag { opacity: .55; }
.diag-yes { color: #1b5e20; font-weight: 700; }
.diag-no { color: #b0b0b0; }
.legend { margin-top: 18px; font-size: 12px; color: #555; }
.legend span { display: inline-block; padding: 2px 8px; border-radius: 3px; margin-right: 6px; font-weight: 700; }
"""


def _conf_color(conf: float) -> str:
    if conf >= 0.8:
        return "#2e7d32"
    if conf >= 0.6:
        return "#f9a825"
    return "#c62828"


def _mark_cell(mark: str) -> str:
    bg, fg, tip = _MARK_STYLE.get(mark, ("#ffffff", "#000000", mark))
    return (
        f'<td class="mark" style="background:{bg};color:{fg}" title="{escape(tip)}">'
        f"{escape(mark)}</td>"
    )


def _ranking_table(hypothesis_names: dict, scores: dict, ranking: list) -> str:
    rows = []
    for i, hid in enumerate(ranking, start=1):
        s = scores[hid]
        cls = "rank-1" if i == 1 else ""
        rows.append(
            f'<tr class="{cls}">'
            f"<td>{i}</td>"
            f"<td>{escape(hypothesis_names.get(hid, hid))} "
            f'<span class="hyp-id">({escape(hid)})</span></td>'
            f'<td class="score">{s["inconsistency"]:.1f}</td>'
            f'<td class="score">{s["support"]:.1f}</td>'
            f'<td class="score">{s["against"]}</td>'
            f'<td class="score">{s["for"]}</td>'
            f'<td class="score">{s["na"]}</td>'
            f"</tr>"
        )
    return (
        '<table class="rank-table"><thead><tr>'
        "<th>#</th><th>Hypothesis</th><th>Inconsistency</th><th>Support</th>"
        "<th>Against</th><th>For</th><th>N/A</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _matrix_table(rows, hypothesis_names: dict) -> str:
    hyp_ids = list(hypothesis_names.keys())
    header = ['<th class="date">Date</th>', "<th>Article</th>"]
    for hid in hyp_ids:
        header.append(
            f'<th class="hyp-col">{escape(hypothesis_names[hid])}'
            f'<br><span class="hyp-id">{escape(hid)}</span></th>'
        )
    header.append("<th>Confidence</th>")
    header.append("<th>Diagnostic</th>")

    body = []
    for row in rows:
        tr_cls = "" if row.is_diagnostic else "nondiag"
        date_str = row.published_date.strftime("%Y-%m-%d") if row.published_date else "—"
        src = f'<div class="src">{escape(row.source)}</div>' if row.source else ""
        cells = [
            f'<td class="date">{date_str}</td>',
            f'<td class="article">{escape(row.title or row.article_id)}{src}</td>',
        ]
        for hid in hyp_ids:
            cells.append(_mark_cell(row.marks.get(hid, "N/A")))
        pct = round(row.confidence * 100)
        cells.append(
            '<td class="conf-wrap">'
            f'<div class="conf-bar"><div class="conf-fill" '
            f'style="width:{pct}%;background:{_conf_color(row.confidence)}"></div></div>'
            f'<div class="conf-pct">{pct}%</div></td>'
        )
        if row.is_diagnostic:
            cells.append('<td class="diag-yes" title="Distinguishes the hypotheses">✓</td>')
        else:
            cells.append('<td class="diag-no" title="Consistent with all hypotheses — no diagnostic value">✗</td>')
        body.append(f'<tr class="{tr_cls}">' + "".join(cells) + "</tr>")

    return (
        "<table><thead><tr>" + "".join(header) + "</tr></thead><tbody>"
        + "".join(body) + "</tbody></table>"
    )


def _legend() -> str:
    items = []
    for mark in ("++", "+", "N/A", "-", "--"):
        bg, fg, tip = _MARK_STYLE[mark]
        items.append(f'<span style="background:{bg};color:{fg}">{escape(mark)}</span>{escape(tip)}')
    return '<div class="legend"><b>Marks:</b> ' + "&nbsp;&nbsp;".join(items) + "</div>"


def render_matrix_html(rows, hypothesis_names, scores, ranking, generated_at) -> str:
    """Render the full ACH matrix HTML document.

    Args:
        rows: EvidenceRow list, already sorted most-recent-first.
        hypothesis_names: ordered dict-like {hyp_id: name} (column order).
        scores: per-hypothesis scores from ``compute_scores``.
        ranking: hypothesis ids most-likely-first (lowest inconsistency).
        generated_at: human-readable timestamp string.

    Returns:
        A self-contained HTML document string.
    """
    most_likely = (
        f"{escape(hypothesis_names.get(ranking[0], ranking[0]))}" if ranking else "—"
    )
    body_ranking = (
        _ranking_table(hypothesis_names, scores, ranking)
        if ranking
        else "<p>No hypotheses scored yet.</p>"
    )
    body_matrix = (
        _matrix_table(rows, hypothesis_names)
        if rows
        else "<p>No evidence rows yet — run the pipeline to populate the matrix.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>ACH Decision Matrix</title><style>{_CSS}</style></head>
<body>
<h1>ACH Decision Matrix</h1>
<div class="meta">{len(rows)} evidence items &middot; {len(hypothesis_names)} hypotheses &middot; generated {escape(generated_at)}</div>

<h2 style="font-size:15px;margin-bottom:2px">Hypothesis ranking</h2>
<div class="note">Most likely = lowest inconsistency (evidence against), per Heuer Step 5 — not the most supporting evidence. Current lead: <b>{most_likely}</b>.</div>
{body_ranking}

<h2 style="font-size:15px;margin-bottom:2px">Evidence matrix</h2>
<div class="note">Each row is one article (evidence), most recent first. Cells show how the article bears on each hypothesis.</div>
{body_matrix}
{_legend()}
</body></html>
"""
