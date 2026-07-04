"""Base agent class and state schemas for ACH Forecasting Agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ArticleData(BaseModel):
    """Schema for a single article."""

    article_id: str = Field(..., description="Unique identifier for the article")
    title: str = Field(..., description="Article title")
    url: str = Field(..., description="Article URL")
    content: str = Field(..., description="Article body text")
    published_date: Optional[datetime] = Field(None, description="Article publication date")
    source: str = Field(default="reuters", description="News source")


class HypothesisScore(BaseModel):
    """Schema for a single hypothesis score."""

    hypothesis_id: str = Field(..., description="Hypothesis ID (h1, h2, h3)")
    hypothesis_name: str = Field(..., description="Human-readable hypothesis name")
    evidence_mark: str = Field(
        ..., description="Evidence mark: ++, +, N/A, -, --"
    )
    confidence: float = Field(
        ..., description="Confidence score (0.0-1.0) from self-consistency", ge=0.0, le=1.0
    )
    reasoning: str = Field(..., description="Brief explanation for the score")


class AssessmentResult(BaseModel):
    """Schema for an assessment result.

    Carries enough article metadata (title/source/date) for the Matrix Agent to
    build a self-contained evidence row without re-joining against ArticleData.
    """

    article_id: str = Field(..., description="Reference to the article being assessed")
    article_title: str = Field(default="", description="Article title (for the matrix row)")
    article_url: str = Field(default="", description="Article URL (for the matrix row link)")
    article_source: str = Field(default="", description="Article source (for the matrix row)")
    article_published_date: Optional[datetime] = Field(
        default=None, description="Article publication date (for sorting the matrix)"
    )
    hypothesis_scores: list[HypothesisScore] = Field(
        ..., description="Scores for each hypothesis"
    )
    overall_confidence: float = Field(
        ..., description="Overall confidence in the assessment (0.0-1.0)", ge=0.0, le=1.0
    )
    flagged_for_human_review: bool = Field(
        ..., description="True if confidence < threshold or conflicting signals"
    )
    assessment_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the assessment was performed"
    )


class EvidenceRow(BaseModel):
    """One row of the ACH matrix: an article (evidence item) and its per-hypothesis marks.

    This is the Heuer Chapter 8 layout — evidence down the side, hypotheses
    across the top — preserving the per-article audit trail.
    """

    article_id: str = Field(..., description="Article this evidence row represents")
    title: str = Field(default="", description="Article title")
    url: str = Field(default="", description="Article URL")
    source: str = Field(default="", description="Article source")
    published_date: Optional[datetime] = Field(default=None, description="Article publication date")
    marks: dict[str, str] = Field(
        ..., description="Evidence mark per hypothesis id, e.g. {'h1': 'N/A', 'h2': '++'}"
    )
    confidence: float = Field(
        default=0.0, description="Self-consistency confidence for this article (0.0-1.0)", ge=0.0, le=1.0
    )

    @property
    def is_diagnostic(self) -> bool:
        """Diagnostic if the evidence distinguishes hypotheses (marks are not all equal).

        Per Heuer, evidence consistent with every hypothesis has no diagnostic value.
        """
        return len(set(self.marks.values())) > 1


@dataclass
class ScraperAgentState:
    """State for the Scraper Agent."""

    iteration_id: str
    articles: list[ArticleData] = field(default_factory=list)
    next_page_token: Optional[str] = None
    last_crawl_time: Optional[datetime] = None
    urls_processed: set[str] = field(default_factory=set)


@dataclass
class AssessmentAgentState:
    """State for the Assessment Agent."""

    article: ArticleData
    hypothesis_scores: list[HypothesisScore] = field(default_factory=list)
    overall_confidence: float = 0.0
    flagged_for_human_review: bool = False
    assessment_timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MatrixAgentState:
    """State for the Matrix Agent.

    The matrix is a list of per-article evidence rows plus the ordered set of
    hypotheses (id -> name) that form the columns.
    """

    matrix_version: str
    evidence_rows: list[EvidenceRow] = field(default_factory=list)
    hypothesis_names: dict[str, str] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.utcnow)
    nation_id: str = ""

    @property
    def article_count(self) -> int:
        return len(self.evidence_rows)
