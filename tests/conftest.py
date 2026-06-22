"""Shared pytest fixtures.

All tests are hermetic: no network, no Ollama, no real filesystem. External HTTP
is mocked and file I/O is confined to pytest's ``tmp_path``.
"""

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.base import ArticleData, AssessmentResult, HypothesisScore  # noqa: E402
from config.settings import Settings  # noqa: E402


@pytest.fixture
def config(tmp_path):
    """A Settings instance with storage pointed at a throwaway temp directory."""
    s = Settings()
    s.data_dir = tmp_path / "data"
    s.logs_dir = tmp_path / "logs"
    s.evidence_marks = ["++", "+", "N/A", "-", "--"]
    s.confidence_threshold = 0.6
    s.llm_num_passes = 3
    s.scraper_max_articles = 25
    s.scraper_max_retries = 2
    s.scraper_backoff_factor = 1.0
    s.scraper_timeout_seconds = 5
    s.matrix_storage_cap_gb = 1.0
    s.use_system_truststore = False  # don't touch the OS trust store in tests
    return s


@pytest.fixture
def hypotheses():
    """The three competing default hypotheses."""
    return [
        {"id": "h1", "name": "China supports US position", "description": "China aligns with the US."},
        {"id": "h2", "name": "China maintains neutrality", "description": "China stays neutral."},
        {"id": "h3", "name": "China supports Iran position", "description": "China aligns with Iran."},
    ]


@pytest.fixture
def article():
    """A single representative article."""
    return ArticleData(
        article_id="guardian/world/2026/jun/22/sample",
        title="China's foreign minister comments on US-Iran talks",
        url="https://www.theguardian.com/world/2026/jun/22/sample",
        content="China's foreign minister Wang Yi welcomed Iran to ongoing talks.",
        source="The Guardian",
    )


def _make_assessment(article_id, marks, confidence=1.0, flagged=False,
                     title="", source="The Guardian", published_date=None):
    """Build an AssessmentResult from a {hypothesis_id: mark} dict."""
    scores = [
        HypothesisScore(
            hypothesis_id=hid,
            hypothesis_name=f"Hypothesis {hid}",
            evidence_mark=mark,
            confidence=confidence,
            reasoning="test",
        )
        for hid, mark in marks.items()
    ]
    return AssessmentResult(
        article_id=article_id,
        article_title=title or f"Article {article_id}",
        article_source=source,
        article_published_date=published_date,
        hypothesis_scores=scores,
        overall_confidence=confidence,
        flagged_for_human_review=flagged,
    )


@pytest.fixture
def assessment_factory():
    """Factory: assessment_factory("art1", {"h1": "++", "h2": "N/A", "h3": "-"})."""
    return _make_assessment
