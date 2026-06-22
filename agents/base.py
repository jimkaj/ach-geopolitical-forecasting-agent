"""Base agent class and state schemas for ACH Forecasting Agent."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

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
    """Schema for an assessment result."""

    article_id: str = Field(..., description="Reference to the article being assessed")
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


class MatrixAggregation(BaseModel):
    """Schema for aggregated evidence in the ACH matrix."""

    hypothesis_id: str = Field(..., description="Hypothesis ID")
    hypothesis_name: str = Field(...)
    evidence_tally: dict[str, int] = Field(
        default_factory=lambda: {"++": 0, "+": 0, "N/A": 0, "-": 0, "--": 0},
        description="Cumulative count of evidence marks",
    )
    net_support: float = Field(
        default=0.0, description="Cumulative support score (++ weighted +2, + +1, N/A 0, - -1, -- -2)"
    )


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
    """State for the Matrix Agent."""

    matrix_version: str
    hypothesis_aggregates: dict[str, MatrixAggregation] = field(default_factory=dict)
    article_count: int = 0
    last_update: datetime = field(default_factory=datetime.utcnow)
    total_storage_used_mb: float = 0.0
