"""Render the ACH decision matrix as a self-contained, color-coded HTML page.

Layout follows Heuer Chapter 8: evidence (articles) down the rows, hypotheses
across the columns, with a per-hypothesis inconsistency ranking (lowest = most
likely). Pure presentation — no I/O, no domain logic.

v3 additions:
- _compute_score_series: derives cumulative US-alignment score from evidence marks
- _render_line_graph: embeds a pure-JS Canvas chart into each nation's ACH page
- render_summary_html: all-nations overview page with multi-line chart and nav links
- render_matrix_html: gains `title` and `return_url` parameters
"""

import json
from html import escape

# Per-mark cell styling (background, text color, tooltip).
_MARK_STYLE = {
    "++": ("#1b5e20", "#ffffff", "Strong support"),
    "+": ("#66bb6a", "#0b2e13", "Weak support"),
    "N/A": ("#e0e0e0", "#555555", "Not relevant / no evidence"),
    "-": ("#ef9a9a", "#3b0d0d", "Weak evidence against"),
    "--": ("#b71c1c", "#ffffff", "Strong evidence against"),
}

# Score weights for the US-alignment line graph.
# contribution per article = weight[h1_mark] - weight[h3_mark]
_MARK_WEIGHT = {"++": 2, "+": 1, "N/A": 0, "-": -1, "--": -2}

# Colour palette for the multi-nation summary chart (cycles if > 8 nations).
_NATION_COLORS = [
    "#2563eb",  # blue
    "#dc2626",  # red
    "#16a34a",  # green
    "#d97706",  # amber
    "#7c3aed",  # violet
    "#0891b2",  # cyan
    "#be185d",  # pink
    "#059669",  # emerald
    "#ea580c",  # orange
    "#6366f1",  # indigo
]

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
.article a { color: #2563eb; text-decoration: none; }
.article a:hover { text-decoration: underline; }
.back-btn { display:inline-block; padding:6px 14px; background:#2563eb; color:#fff;
            text-decoration:none; border-radius:4px; font-size:13px; margin-bottom:16px; }
.back-btn:hover { background:#1d4ed8; }
.chart-section { margin-bottom: 28px; }
.chart-wrap { position:relative; display:inline-block; }
.chart-tip { position:absolute; display:none; background:rgba(15,23,42,0.88); color:#fff;
             padding:6px 10px; border-radius:4px; font-size:12px; pointer-events:none;
             white-space:nowrap; z-index:10; max-width:300px; }
.nation-legend { margin-top: 10px; }
.nation-legend a { display:inline-block; margin-right:18px; font-size:13px; font-weight:600;
                   text-decoration:none; padding:3px 0; border-bottom:3px solid; }
.nation-legend a:hover { opacity:0.75; }
"""


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------

def _compute_score_series(evidence_rows, hypothesis_names: dict) -> list:
    """Derive cumulative US-alignment score series from evidence rows.

    Scoring (confirmed v3 design):
      contribution per article = weight[h1_mark] - weight[h3_mark]
      h2 (neutral) contributes 0 — it is the midpoint of the axis.

    h1 = first hypothesis key (supports US), h3 = last hypothesis key (opposes US).
    Rows without a published_date are excluded.

    Returns:
        List of [date_str, cumulative_score, title] sorted oldest-first.
    """
    hyp_ids = list(hypothesis_names.keys())
    if len(hyp_ids) < 3:
        return []
    h1_id = hyp_ids[0]
    h3_id = hyp_ids[-1]

    dated = []
    for row in evidence_rows:
        if row.published_date is None:
            continue
        h1_w = _MARK_WEIGHT.get(row.marks.get(h1_id, "N/A"), 0)
        h3_w = _MARK_WEIGHT.get(row.marks.get(h3_id, "N/A"), 0)
        dated.append((row.published_date, h1_w - h3_w, row.title or row.article_id))

    dated.sort(key=lambda x: x[0])

    result = []
    cumulative = 0
    for dt, contrib, title in dated:
        cumulative += contrib
        result.append([dt.strftime("%Y-%m-%d"), cumulative, title])
    return result


# ---------------------------------------------------------------------------
# Line graph renderer (single nation)
# ---------------------------------------------------------------------------

def _render_line_graph(series_data: list, chart_id: str, nation_label: str) -> str:
    """Return an HTML block containing a canvas line chart for one nation.

    Args:
        series_data: Output of _compute_score_series — list of [date, score, title].
        chart_id:    Unique element ID prefix (used for canvas + tooltip div).
        nation_label: Display name shown in the chart heading.
    """
    if not series_data:
        return (
            '<div class="chart-section">'
            f'<p class="note">No dated evidence rows yet for {escape(nation_label)} — '
            "run the pipeline to populate the alignment chart.</p></div>"
        )

    data_json = json.dumps(series_data, ensure_ascii=False)
    tip_id = f"{chart_id}_tip"

    js = f"""(function(){{
  'use strict';
  var pts={data_json};
  if(!pts.length)return;
  var canvas=document.getElementById('{chart_id}');
  if(!canvas)return;
  var ctx=canvas.getContext('2d');
  var W=canvas.width,H=canvas.height;
  var PL=58,PR=24,PT=22,PB=54;
  var cW=W-PL-PR,cH=H-PT-PB;

  var dts=pts.map(function(p){{return new Date(p[0]+'T00:00:00');}});
  var sc=pts.map(function(p){{return p[1];}});

  var t0=dts[0].getTime(),t1=dts[dts.length-1].getTime();
  var tRng=t1-t0||1;
  var sMax=Math.max.apply(null,sc.concat([1]));
  var sMin=Math.min.apply(null,sc.concat([-1]));
  var pad2=Math.max(1,(sMax-sMin)*0.15);
  var sLo=sMin-pad2,sHi=sMax+pad2,sRng=sHi-sLo;

  function xf(d){{return PL+((d.getTime()-t0)/tRng)*cW;}}
  function yf(s){{return PT+cH*(1-(s-sLo)/sRng);}}
  var y0=yf(0);

  // Positive fill
  ctx.save();
  ctx.beginPath();ctx.rect(PL,PT,cW,Math.max(0,y0-PT));ctx.clip();
  var gP=ctx.createLinearGradient(0,PT,0,y0);
  gP.addColorStop(0,'rgba(22,163,74,0.22)');gP.addColorStop(1,'rgba(22,163,74,0.03)');
  ctx.fillStyle=gP;
  ctx.beginPath();ctx.moveTo(xf(dts[0]),y0);
  dts.forEach(function(d,i){{ctx.lineTo(xf(d),yf(sc[i]));}});
  ctx.lineTo(xf(dts[dts.length-1]),y0);ctx.closePath();ctx.fill();
  ctx.restore();

  // Negative fill
  ctx.save();
  ctx.beginPath();ctx.rect(PL,y0,cW,Math.max(0,PT+cH-y0));ctx.clip();
  var gN=ctx.createLinearGradient(0,y0,0,PT+cH);
  gN.addColorStop(0,'rgba(220,38,38,0.03)');gN.addColorStop(1,'rgba(220,38,38,0.22)');
  ctx.fillStyle=gN;
  ctx.beginPath();ctx.moveTo(xf(dts[0]),y0);
  dts.forEach(function(d,i){{ctx.lineTo(xf(d),yf(sc[i]));}});
  ctx.lineTo(xf(dts[dts.length-1]),y0);ctx.closePath();ctx.fill();
  ctx.restore();

  // Grid lines
  var gSteps=5;
  for(var gi=0;gi<=gSteps;gi++){{
    var gv=sLo+sRng*gi/gSteps;
    ctx.strokeStyle='#ececec';ctx.lineWidth=0.8;
    ctx.beginPath();ctx.moveTo(PL,yf(gv));ctx.lineTo(PL+cW,yf(gv));ctx.stroke();
  }}

  // Zero line
  ctx.strokeStyle='#bbb';ctx.lineWidth=1;ctx.setLineDash([5,4]);
  ctx.beginPath();ctx.moveTo(PL,y0);ctx.lineTo(PL+cW,y0);ctx.stroke();
  ctx.setLineDash([]);

  // Axes
  ctx.strokeStyle='#ccc';ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(PL,PT);ctx.lineTo(PL,PT+cH);ctx.stroke();
  ctx.beginPath();ctx.moveTo(PL,PT+cH);ctx.lineTo(PL+cW,PT+cH);ctx.stroke();

  // Y-axis labels
  ctx.fillStyle='#666';ctx.font='11px sans-serif';ctx.textAlign='right';
  for(var yi=0;yi<=gSteps;yi++){{
    var yv=sLo+sRng*yi/gSteps;
    ctx.fillText(Math.round(yv),PL-5,yf(yv)+4);
  }}
  ctx.save();ctx.fillStyle='#999';ctx.font='10px sans-serif';
  ctx.translate(13,PT+cH/2);ctx.rotate(-Math.PI/2);
  ctx.textAlign='center';ctx.fillText('Cumulative score',0,0);ctx.restore();

  // X-axis labels (≤6 ticks)
  ctx.textAlign='center';ctx.fillStyle='#666';ctx.font='11px sans-serif';
  var nT=Math.min(6,pts.length);
  var shown={{}};
  for(var ti=0;ti<nT;ti++){{
    var idx=nT>1?Math.round(ti*(pts.length-1)/(nT-1)):0;
    var xp=xf(dts[idx]);
    if(!shown[pts[idx][0]]){{
      ctx.fillText(pts[idx][0],xp,PT+cH+16);shown[pts[idx][0]]=1;
    }}
    ctx.strokeStyle='#e5e5e5';ctx.lineWidth=0.5;
    ctx.beginPath();ctx.moveTo(xp,PT);ctx.lineTo(xp,PT+cH);ctx.stroke();
  }}

  // Line
  ctx.strokeStyle='#2563eb';ctx.lineWidth=2.5;ctx.lineJoin='round';
  ctx.beginPath();
  dts.forEach(function(d,i){{i===0?ctx.moveTo(xf(d),yf(sc[i])):ctx.lineTo(xf(d),yf(sc[i]));}});
  ctx.stroke();

  // Dots
  dts.forEach(function(d,i){{
    ctx.beginPath();ctx.arc(xf(d),yf(sc[i]),4.5,0,Math.PI*2);
    ctx.fillStyle=sc[i]>=0?'#16a34a':'#dc2626';
    ctx.strokeStyle='#fff';ctx.lineWidth=1.5;ctx.fill();ctx.stroke();
  }});

  // Tooltip
  var tip=document.getElementById('{tip_id}');
  canvas.addEventListener('mousemove',function(e){{
    var r=canvas.getBoundingClientRect();
    var mx=(e.clientX-r.left)*(W/r.width);
    var my=(e.clientY-r.top)*(H/r.height);
    var best=-1,bestD=Infinity;
    dts.forEach(function(d,i){{
      var dd=Math.hypot(xf(d)-mx,yf(sc[i])-my);
      if(dd<bestD){{bestD=dd;best=i;}}
    }});
    if(tip){{
      if(bestD<14){{
        var ttl=pts[best][2]?pts[best][2].substring(0,60)+(pts[best][2].length>60?'…':''):'';
        tip.innerHTML='<b>'+pts[best][0]+'</b> &middot; Score: <b>'+sc[best]+'</b><br>'+ttl;
        var tx=xf(dts[best])+12,ty=yf(sc[best])-38;
        if(tx+220>W)tx=xf(dts[best])-230;
        if(ty<PT)ty=yf(sc[best])+8;
        tip.style.left=tx+'px';tip.style.top=ty+'px';tip.style.display='block';
      }}else{{tip.style.display='none';}}
    }}
  }});
  if(tip)canvas.addEventListener('mouseleave',function(){{tip.style.display='none';}});
}})();"""

    return f"""<div class="chart-section">
<h2 style="font-size:15px;margin:0 0 4px">US-Alignment Score Over Time — {escape(nation_label)}</h2>
<div class="note">Cumulative score: h1 (supports US) adds points, h3 (opposes US) subtracts. Zero = neutral baseline.</div>
<div class="chart-wrap">
  <canvas id="{chart_id}" width="860" height="260"
    style="display:block;border:1px solid #ddd;border-radius:4px;background:#fff"></canvas>
  <div id="{tip_id}" class="chart-tip"></div>
</div>
<script>{js}</script>
</div>"""


# ---------------------------------------------------------------------------
# Existing private helpers (unchanged)
# ---------------------------------------------------------------------------

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
        title_text = escape(row.title or row.article_id)
        title_html = (
            f'<a href="{escape(row.url)}" target="_blank" rel="noopener">{title_text}</a>'
            if row.url
            else title_text
        )
        cells = [
            f'<td class="date">{date_str}</td>',
            f'<td class="article">{title_html}{src}</td>',
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


# ---------------------------------------------------------------------------
# Public: per-nation ACH matrix page
# ---------------------------------------------------------------------------

def render_matrix_html(
    rows,
    hypothesis_names,
    scores,
    ranking,
    generated_at,
    title: str = "ACH Decision Matrix",
    return_url: str = "",
) -> str:
    """Render the full ACH matrix HTML document for one nation.

    Args:
        rows: EvidenceRow list, already sorted most-recent-first.
        hypothesis_names: ordered dict-like {hyp_id: name} (column order).
        scores: per-hypothesis scores from ``compute_scores``.
        ranking: hypothesis ids most-likely-first (lowest inconsistency).
        generated_at: human-readable timestamp string.
        title: Page/heading title (default "ACH Decision Matrix").
        return_url: If non-empty, a "← Back to Summary" button links here.

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

    back_html = (
        f'<a href="{escape(return_url)}" class="back-btn">&#8592; Back to Summary</a><br>'
        if return_url
        else ""
    )

    # Line graph uses all rows (the function re-sorts by date internally).
    score_series = _compute_score_series(rows, hypothesis_names)
    chart_id = "alignChart"
    graph_html = _render_line_graph(score_series, chart_id, title)

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)}</title><style>{_CSS}</style></head>
<body>
{back_html}
<h1>{escape(title)}</h1>
<div class="meta">{len(rows)} evidence items &middot; {len(hypothesis_names)} hypotheses &middot; generated {escape(generated_at)}</div>

<h2 style="font-size:15px;margin-bottom:2px">Hypothesis ranking</h2>
<div class="note">Most likely = lowest inconsistency (evidence against), per Heuer Step 5 — not the most supporting evidence. Current lead: <b>{most_likely}</b>.</div>
{body_ranking}

{graph_html}

<h2 style="font-size:15px;margin-bottom:2px">Evidence matrix</h2>
<div class="note">Each row is one article (evidence), most recent first. Cells show how the article bears on each hypothesis.</div>
{body_matrix}
{_legend()}
</body></html>
"""


# ---------------------------------------------------------------------------
# Public: all-nations summary page
# ---------------------------------------------------------------------------

def render_summary_html(nation_states: dict) -> str:
    """Render the all-nations overview page with a multi-line alignment chart.

    Args:
        nation_states: {nation_id: MatrixAgentState} for every processed nation.

    Returns:
        A self-contained HTML document string saved as data/matrix/summary.html.
        Each nation's legend entry and chart line links to
        {nation_id}/acch_matrix.html (relative path).
    """
    # Build per-nation series data
    series = []
    for i, (nation_id, state) in enumerate(nation_states.items()):
        score_series = _compute_score_series(state.evidence_rows, state.hypothesis_names)
        color = _NATION_COLORS[i % len(_NATION_COLORS)]
        label = nation_id.replace("_", " ").title()
        href = f"{nation_id}/acch_matrix.html"
        series.append({
            "label": label,
            "color": color,
            "href": href,
            "points": [[p[0], p[1]] for p in score_series],  # [date, score] only
        })

    series_json = json.dumps(series, ensure_ascii=False)

    # Legend entries (clickable links below chart)
    legend_links = []
    for s in series:
        legend_links.append(
            f'<a href="{escape(s["href"])}" '
            f'style="color:{escape(s["color"])};border-color:{escape(s["color"])}">'
            f'{escape(s["label"])}</a>'
        )
    legend_html = (
        '<div class="nation-legend">' + "".join(legend_links) + "</div>"
        if legend_links else ""
    )

    js = f"""(function(){{
  'use strict';
  var series={series_json};
  var canvas=document.getElementById('summaryChart');
  if(!canvas||!series.length)return;
  var ctx=canvas.getContext('2d');
  var W=canvas.width,H=canvas.height;
  var PL=58,PR=24,PT=22,PB=54;
  var cW=W-PL-PR,cH=H-PT-PB;

  // Precompute Date objects and flatten for range detection
  var allT=[],allSc=[];
  series.forEach(function(s){{
    s._dts=s.points.map(function(p){{return new Date(p[0]+'T00:00:00');}});
    s._sc=s.points.map(function(p){{return p[1];}});
    s._dts.forEach(function(d){{allT.push(d.getTime());}});
    allSc=allSc.concat(s._sc);
  }});
  if(!allT.length)return;

  var t0=Math.min.apply(null,allT),t1=Math.max.apply(null,allT);
  var tRng=t1-t0||1;
  var sMax=Math.max.apply(null,allSc.concat([1]));
  var sMin=Math.min.apply(null,allSc.concat([-1]));
  var pad2=Math.max(1,(sMax-sMin)*0.15);
  var sLo=sMin-pad2,sHi=sMax+pad2,sRng=sHi-sLo;

  function xf(ts){{return PL+((ts-t0)/tRng)*cW;}}
  function yf(s){{return PT+cH*(1-(s-sLo)/sRng);}}
  var y0=yf(0);

  // Grid
  var gSteps=5;
  for(var gi=0;gi<=gSteps;gi++){{
    var gv=sLo+sRng*gi/gSteps;
    ctx.strokeStyle='#ececec';ctx.lineWidth=0.8;
    ctx.beginPath();ctx.moveTo(PL,yf(gv));ctx.lineTo(PL+cW,yf(gv));ctx.stroke();
  }}

  // Zero line
  ctx.strokeStyle='#bbb';ctx.lineWidth=1;ctx.setLineDash([5,4]);
  ctx.beginPath();ctx.moveTo(PL,y0);ctx.lineTo(PL+cW,y0);ctx.stroke();
  ctx.setLineDash([]);

  // Axes
  ctx.strokeStyle='#ccc';ctx.lineWidth=1;
  ctx.beginPath();ctx.moveTo(PL,PT);ctx.lineTo(PL,PT+cH);ctx.stroke();
  ctx.beginPath();ctx.moveTo(PL,PT+cH);ctx.lineTo(PL+cW,PT+cH);ctx.stroke();

  // Y labels
  ctx.fillStyle='#666';ctx.font='11px sans-serif';ctx.textAlign='right';
  for(var yi=0;yi<=gSteps;yi++){{
    var yv=sLo+sRng*yi/gSteps;
    ctx.fillText(Math.round(yv),PL-5,yf(yv)+4);
  }}
  ctx.save();ctx.fillStyle='#999';ctx.font='10px sans-serif';
  ctx.translate(13,PT+cH/2);ctx.rotate(-Math.PI/2);
  ctx.textAlign='center';ctx.fillText('Cumulative score',0,0);ctx.restore();

  // X labels (6 ticks spanning full range)
  ctx.textAlign='center';ctx.fillStyle='#666';ctx.font='11px sans-serif';
  var nT=6;
  for(var ti=0;ti<nT;ti++){{
    var tv=t0+(t1-t0)*ti/(nT-1);
    var xp=xf(tv);
    var lbl=new Date(tv).toISOString().substring(0,10);
    ctx.fillText(lbl,xp,PT+cH+16);
    ctx.strokeStyle='#e5e5e5';ctx.lineWidth=0.5;
    ctx.beginPath();ctx.moveTo(xp,PT);ctx.lineTo(xp,PT+cH);ctx.stroke();
  }}

  // Draw each nation's line + dots
  series.forEach(function(s){{
    if(!s._dts.length)return;
    ctx.strokeStyle=s.color;ctx.lineWidth=2.5;ctx.lineJoin='round';
    ctx.beginPath();
    s._dts.forEach(function(d,i){{
      i===0?ctx.moveTo(xf(d.getTime()),yf(s._sc[i])):ctx.lineTo(xf(d.getTime()),yf(s._sc[i]));
    }});
    ctx.stroke();
    s._dts.forEach(function(d,i){{
      ctx.beginPath();ctx.arc(xf(d.getTime()),yf(s._sc[i]),4,0,Math.PI*2);
      ctx.fillStyle=s.color;ctx.strokeStyle='#fff';ctx.lineWidth=1.5;
      ctx.fill();ctx.stroke();
    }});
  }});

  // Tooltip + click-to-navigate
  var tip=document.getElementById('summaryChart_tip');
  function findNearest(mx,my){{
    var best=null,bestD=Infinity;
    series.forEach(function(s){{
      s._dts.forEach(function(d,i){{
        var dd=Math.hypot(xf(d.getTime())-mx,yf(s._sc[i])-my);
        if(dd<bestD){{bestD=dd;best={{s:s,i:i,d:bestD}};}}
      }});
    }});
    return best&&bestD<16?best:null;
  }}
  canvas.addEventListener('mousemove',function(e){{
    var r=canvas.getBoundingClientRect();
    var mx=(e.clientX-r.left)*(W/r.width),my=(e.clientY-r.top)*(H/r.height);
    var hit=findNearest(mx,my);
    if(tip){{
      if(hit){{
        tip.innerHTML='<b>'+hit.s.label+'</b> &middot; '+hit.s.points[hit.i][0]+
          ' &middot; Score: <b>'+hit.s._sc[hit.i]+'</b><br><span style="font-size:11px;opacity:.8">Click to view ACH matrix</span>';
        var tx=xf(hit.s._dts[hit.i].getTime())+12,ty=yf(hit.s._sc[hit.i])-44;
        if(tx+250>W)tx=xf(hit.s._dts[hit.i].getTime())-260;
        if(ty<PT)ty=yf(hit.s._sc[hit.i])+8;
        tip.style.left=tx+'px';tip.style.top=ty+'px';tip.style.display='block';
        canvas.style.cursor='pointer';
      }}else{{tip.style.display='none';canvas.style.cursor='default';}}
    }}
  }});
  if(tip)canvas.addEventListener('mouseleave',function(){{tip.style.display='none';canvas.style.cursor='default';}});
  canvas.addEventListener('click',function(e){{
    var r=canvas.getBoundingClientRect();
    var mx=(e.clientX-r.left)*(W/r.width),my=(e.clientY-r.top)*(H/r.height);
    var hit=findNearest(mx,my);
    if(hit)window.location.href=hit.s.href;
  }});
}})();"""

    nation_count = len(nation_states)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>ACH Geopolitical Alignment — Summary</title><style>{_CSS}</style></head>
<body>
<h1>ACH Geopolitical Alignment Summary</h1>
<div class="meta">{nation_count} nation{"s" if nation_count != 1 else ""} tracked &middot; click a line or legend entry to view the full ACH matrix</div>

<h2 style="font-size:15px;margin-bottom:4px">Cumulative US-Alignment Score by Nation</h2>
<div class="note">Above zero = evidence leans toward supporting the US. Below zero = evidence leans toward opposing the US.</div>
<div class="chart-wrap">
  <canvas id="summaryChart" width="860" height="300"
    style="display:block;border:1px solid #ddd;border-radius:4px;background:#fff"></canvas>
  <div id="summaryChart_tip" class="chart-tip"></div>
</div>
{legend_html}
<script>{js}</script>
</body></html>
"""
