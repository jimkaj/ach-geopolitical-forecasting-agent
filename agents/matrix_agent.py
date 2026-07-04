"""Matrix Agent: maintains the ACH decision matrix (Heuer Ch. 8 layout).

The matrix is evidence (articles) down the rows and hypotheses across the
columns. Each cell holds the evidence mark for that article/hypothesis pair.
Hypotheses are ranked by **inconsistency** (evidence against), per Heuer Step 5:
the most likely hypothesis is the one with the *least* evidence against it, not
the most evidence for it.

State persists as JSON (`matrix_state.json`) so evidence rows accumulate across
runs; each run also renders an HTML view (`acch_matrix.html`).
"""

import json
import logging
from datetime import datetime

from tools.matrix_view import render_matrix_html

from .base import AssessmentResult, EvidenceRow, MatrixAgentState


logger = logging.getLogger(__name__)

# Weights for the inconsistency score (evidence *against* a hypothesis).
# Heuer Step 5: rank by inconsistency — lowest score is the most likely hypothesis.
INCONSISTENCY_WEIGHTS = {"--": 2.0, "-": 1.0}
# Weights for supporting evidence (shown for context only; not used for ranking).
SUPPORT_WEIGHTS = {"++": 2.0, "+": 1.0}

STATE_FILENAME = "matrix_state.json"
LATEST_HTML_FILENAME = "acch_matrix.html"

# nation_id.title() replace uae with "United Arab Emirates" (e.g. "uae" -> "United Arab Emirates");
# override acronym nation IDs here so their display name renders correctly.
NATION_NAME_OVERRIDES = {"uae": "United Arab Emirates"}


def _nation_display_name(nation_id: str) -> str:
    return NATION_NAME_OVERRIDES.get(nation_id, nation_id.replace("_", " ").title())


def compute_scores(rows: list[EvidenceRow], hypothesis_ids: list[str]) -> dict[str, dict]:
    """Compute per-hypothesis summary scores across all evidence rows.

    Args:
        rows: Evidence rows (articles) in the matrix.
        hypothesis_ids: Hypothesis ids forming the columns.

    Returns:
        ``{hyp_id: {"inconsistency": float, "support": float,
                    "against": int, "for": int, "na": int}}``
    """
    scores = {
        hid: {"inconsistency": 0.0, "support": 0.0, "against": 0, "for": 0, "na": 0}
        for hid in hypothesis_ids
    }
    for row in rows:
        for hid in hypothesis_ids:
            mark = row.marks.get(hid, "N/A")
            s = scores[hid]
            s["inconsistency"] += INCONSISTENCY_WEIGHTS.get(mark, 0.0)
            s["support"] += SUPPORT_WEIGHTS.get(mark, 0.0)
            if mark in ("-", "--"):
                s["against"] += 1
            elif mark in ("+", "++"):
                s["for"] += 1
            else:
                s["na"] += 1
    return scores


def rank_by_inconsistency(scores: dict[str, dict]) -> list[str]:
    """Order hypotheses most-likely-first: lowest inconsistency, then most support."""
    return sorted(
        scores,
        key=lambda hid: (scores[hid]["inconsistency"], -scores[hid]["support"]),
    )


class MatrixAgent:
    """Tier 3 Agent: maintains the ACH evidence matrix and renders it.

    Responsibilities:
    - Ingest scored evidence from the Assessment Agent as per-article rows
    - Accumulate rows across runs (dedup by article id)
    - Rank hypotheses by inconsistency (Heuer Step 5)
    - Persist JSON state and render a color-coded HTML matrix
    """

    def __init__(self, config, file_manager, nation_id: str):
        """Initialize the Matrix Agent.

        Args:
            config: Settings object with matrix configuration
            file_manager: FileManager used to locate the per-nation matrix directory
            nation_id: Nation this agent tracks (e.g. "china"). Determines the
                       subdirectory under data/matrix/ for all output files.
        """
        self.config = config
        self.file_manager = file_manager
        self.nation_id = nation_id
        self.matrix_dir = file_manager.get_nation_matrix_dir(nation_id)
        self.state_path = self.matrix_dir / STATE_FILENAME

        self.state = self._load_matrix_state()
        self.state.nation_id = nation_id
        logger.info(
            f"MatrixAgent[{nation_id}] initialized (v{self.state.matrix_version}, "
            f"{self.state.article_count} evidence rows carried over)"
        )

    def _load_matrix_state(self) -> MatrixAgentState:
        """Load accumulated matrix state from JSON so rows persist across runs."""
        fresh = MatrixAgentState(
            matrix_version=datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            evidence_rows=[],
            hypothesis_names={},
        )
        if not self.state_path.exists():
            logger.info("No prior matrix state found; starting fresh")
            return fresh

        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            rows = []
            for r in data.get("evidence_rows", []):
                raw_date = r.get("published_date")
                published = datetime.fromisoformat(raw_date) if raw_date else None
                aid = r["article_id"]
                url = r.get("url", "")
                if not url:
                    # Backfill URLs for rows ingested before v3 url tracking.
                    # Guardian article_id is the URL path; webUrl = base + id.
                    url = aid if aid.startswith("http") else f"https://www.theguardian.com/{aid}"
                rows.append(
                    EvidenceRow(
                        article_id=aid,
                        title=r.get("title", ""),
                        url=url,
                        source=r.get("source", ""),
                        published_date=published,
                        marks=r.get("marks", {}),
                        confidence=r.get("confidence", 0.0),
                    )
                )
        except (OSError, ValueError, KeyError) as e:
            logger.error(f"Failed to load matrix state {self.state_path}: {e}; starting fresh")
            return fresh

        logger.info(f"Loaded matrix state: {len(rows)} evidence rows")
        return MatrixAgentState(
            matrix_version=datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            evidence_rows=rows,
            hypothesis_names=data.get("hypothesis_names", {}),
        )

    def ingest_assessment(self, assessment: AssessmentResult) -> None:
        """Add (or replace) the evidence row for one assessed article."""
        # Track hypothesis id -> name (preserves column order across runs).
        for score in assessment.hypothesis_scores:
            self.state.hypothesis_names.setdefault(score.hypothesis_id, score.hypothesis_name)

        row = EvidenceRow(
            article_id=assessment.article_id,
            title=assessment.article_title,
            url=assessment.article_url,
            source=assessment.article_source,
            published_date=assessment.article_published_date,
            marks={s.hypothesis_id: s.evidence_mark for s in assessment.hypothesis_scores},
            confidence=assessment.overall_confidence,
        )

        # Dedup: replace any existing row for this article, else append.
        existing = next(
            (i for i, r in enumerate(self.state.evidence_rows) if r.article_id == row.article_id),
            None,
        )
        if existing is not None:
            self.state.evidence_rows[existing] = row
        else:
            self.state.evidence_rows.append(row)
        self.state.last_update = datetime.utcnow()
        logger.debug(f"Ingested evidence row for article {assessment.article_id}")

    def _sorted_rows(self) -> list[EvidenceRow]:
        """Evidence rows most-recent-first; rows without a date sort last."""
        return sorted(
            self.state.evidence_rows,
            key=lambda r: (r.published_date is not None, r.published_date or datetime.min),
            reverse=True,
        )

    def save_matrix(self) -> None:
        """Persist JSON state and render the HTML matrix."""
        # 1. Canonical machine-readable state (reloaded next run).
        state_doc = {
            "matrix_version": self.state.matrix_version,
            "last_update": self.state.last_update.isoformat(),
            "hypothesis_names": self.state.hypothesis_names,
            "evidence_rows": [
                {
                    "article_id": r.article_id,
                    "title": r.title,
                    "url": r.url,
                    "source": r.source,
                    "published_date": r.published_date.isoformat() if r.published_date else None,
                    "marks": r.marks,
                    "confidence": r.confidence,
                }
                for r in self.state.evidence_rows
            ],
        }
        self.state_path.write_text(json.dumps(state_doc, indent=2), encoding="utf-8")

        # 2. Render the HTML view.
        hypothesis_ids = list(self.state.hypothesis_names.keys())
        scores = compute_scores(self.state.evidence_rows, hypothesis_ids)
        ranking = rank_by_inconsistency(scores)
        html = render_matrix_html(
            rows=self._sorted_rows(),
            hypothesis_names=self.state.hypothesis_names,
            scores=scores,
            ranking=ranking,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            title=f"ACH Decision Matrix — {_nation_display_name(self.nation_id)}",
            return_url="../summary.html",
        )

        # 3. Stable HTML view.
        (self.matrix_dir / LATEST_HTML_FILENAME).write_text(html, encoding="utf-8")

        logger.info(f"Saved matrix state and HTML: {self.nation_id}")

    def execute(self, assessments: list[AssessmentResult]) -> MatrixAgentState:
        """Ingest assessments, persist state, and render HTML."""
        logger.info(f"MatrixAgent[{self.nation_id}] processing {len(assessments)} assessments")

        for assessment in assessments:
            self.ingest_assessment(assessment)

        self.save_matrix()

        logger.info(f"Matrix[{self.nation_id}] updated. Total evidence rows: {self.state.article_count}")
        return self.state
