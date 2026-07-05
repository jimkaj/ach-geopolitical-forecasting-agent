"""One-off maintenance script: re-assess every existing evidence row against the
current LLM model (e.g. after upgrading Settings.llm_model).

Article body text is never persisted in matrix_state.json, so each existing
article is re-fetched from Guardian by its content ID before being re-scored.
Re-ingesting a known article_id overwrites its existing evidence row in place
(MatrixAgent.ingest_assessment upserts by article_id) — nothing is duplicated,
and articles that fail to re-fetch simply keep their prior row untouched.

Usage:
    uv run python scripts/reassess_articles.py
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.assessment_agent import AssessmentAgent
from agents.base import ArticleData
from agents.matrix_agent import MatrixAgent
from config import settings
from main import load_domain_whitelist, load_hypothesis_config
from tools.file_manager import FileManager
from tools.git_sync import sync_matrix_to_git
from tools.llm_interface import LLMInterface
from tools.matrix_view import render_summary_html
from tools.web_scraper import WebScraper

logger = logging.getLogger(__name__)


def reassess_all() -> None:
    logger.info(f"Re-assessing all existing articles with model: {settings.llm_model}")

    nations_config = load_hypothesis_config(PROJECT_ROOT / "config" / "hypothesis_config.yaml")
    domain_whitelist = load_domain_whitelist(PROJECT_ROOT / "config" / "domain_whitelist.txt")

    file_manager = FileManager(settings)
    llm_interface = LLMInterface(settings)
    web_scraper = WebScraper(settings, domain_whitelist)

    results_by_nation: dict = {}

    for nation_id, nation_cfg in nations_config.items():
        hypotheses = nation_cfg.get("hypotheses", [])
        matrix_agent = MatrixAgent(settings, file_manager, nation_id=nation_id)

        if not matrix_agent.state.evidence_rows:
            logger.info(f"[{nation_id}] No existing evidence rows; skipping")
            results_by_nation[nation_id] = matrix_agent.state
            continue

        articles = []
        for row in matrix_agent.state.evidence_rows:
            parsed = web_scraper.fetch_article_by_id(row.article_id)
            if parsed is None:
                logger.warning(
                    f"[{nation_id}] Could not re-fetch {row.article_id}; keeping existing row"
                )
                continue
            articles.append(ArticleData(**parsed))

        logger.info(f"[{nation_id}] Re-assessing {len(articles)} article(s)")
        assessment_agent = AssessmentAgent(settings, hypotheses, llm_interface)
        assessments = assessment_agent.execute(articles)

        matrix_state = matrix_agent.execute(assessments)
        results_by_nation[nation_id] = matrix_state

    logger.info("Writing summary.html")
    summary_html = render_summary_html(results_by_nation)
    summary_path = settings.data_dir / "matrix" / "summary.html"
    summary_path.write_text(summary_html, encoding="utf-8")

    if settings.auto_git_sync:
        sync_matrix_to_git(PROJECT_ROOT, settings.data_dir)

    logger.info("Reassessment complete")


if __name__ == "__main__":
    try:
        reassess_all()
    except KeyboardInterrupt:
        logger.info("Reassessment interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
