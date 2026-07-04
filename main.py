"""
Main orchestrator for the ACH Forecasting Agent — v3 Multi-Nation.

Applies Analysis of Competing Hypotheses to Guardian news articles across
multiple nations, each with three fixed hypotheses on the US-alignment axis:
  h1: [Nation] supports the United States
  h2: [Nation] maintains a neutral stance with the United States
  h3: [Nation] opposes the United States

Each nation gets its own isolated ACH matrix, line graph, and HTML page.
A summary page at data/matrix/summary.html shows all nations on one chart.

Usage:
    uv run python main.py
"""

import logging
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.assessment_agent import AssessmentAgent
from agents.matrix_agent import MatrixAgent
from agents.scraper_agent import ScraperAgent
from config import settings
from tools.audit_logger import setup_audit_logging, setup_console_logging, AuditLogger
from tools.file_manager import FileManager
from tools.llm_interface import LLMInterface
from tools.matrix_view import render_summary_html
from tools.web_scraper import WebScraper


setup_audit_logging(settings.logs_dir)
setup_console_logging(settings.enable_debug_logging)
logger = logging.getLogger(__name__)


def render_nation_matrix(matrix_state, nation_id: str) -> None:
    """Print the hypothesis ranking for one nation to stdout."""
    from agents.matrix_agent import compute_scores, rank_by_inconsistency

    names = matrix_state.hypothesis_names
    hyp_ids = list(names.keys())
    scores = compute_scores(matrix_state.evidence_rows, hyp_ids)
    ranking = rank_by_inconsistency(scores)
    html_path = settings.data_dir / "matrix" / nation_id / "acch_matrix.html"

    try:
        from rich.console import Console
        from rich.table import Table

        label = nation_id.replace("_", " ").title()
        table = Table(
            title=f"ACH Ranking — {label} (most likely first = lowest inconsistency)",
            title_style="bold",
        )
        table.add_column("#", justify="right")
        table.add_column("Hypothesis", style="cyan")
        table.add_column("Inconsistency", justify="right", style="bold")
        table.add_column("Support", justify="right")
        table.add_column("Against/For/N/A", justify="right")

        for i, hid in enumerate(ranking, start=1):
            s = scores[hid]
            row_style = "green" if i == 1 else ""
            table.add_row(
                str(i), names.get(hid, hid), f"{s['inconsistency']:.1f}",
                f"{s['support']:.1f}", f"{s['against']}/{s['for']}/{s['na']}",
                style=row_style,
            )
        console = Console()
        console.print()
        console.print(table)
        console.print(
            f"[dim]{matrix_state.article_count} evidence rows | full matrix: {html_path}[/dim]"
        )
    except ImportError:
        print(f"\nACH Ranking — {nation_id}:")
        for i, hid in enumerate(ranking, start=1):
            s = scores[hid]
            print(f"  {i}. {names.get(hid, hid)}: inconsistency={s['inconsistency']:.1f}")
        print(f"  Full matrix: {html_path}")


def load_hypothesis_config(config_path: Path) -> dict:
    """Load v3 nation-keyed hypothesis configuration from YAML.

    Returns:
        {nation_id: {"search_query": str, "hypotheses": list[dict]}}
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Hypothesis config not found: {config_path}")

    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)

    nations = config_data.get("nations", {})
    if not nations:
        raise ValueError("hypothesis_config.yaml must have a 'nations' key with at least one entry")

    logger.info(f"Loaded {len(nations)} nations from config: {list(nations)}")
    return nations


def load_domain_whitelist(whitelist_path: Path) -> set[str]:
    """Load domain whitelist from text file."""
    if not whitelist_path.exists():
        raise FileNotFoundError(f"Domain whitelist not found: {whitelist_path}")

    domains = set()
    with open(whitelist_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                domains.add(line)

    logger.info(f"Loaded {len(domains)} whitelisted domains")
    return domains


def run_agent_pipeline() -> None:
    """Execute the multi-nation three-agent pipeline.

    Each nation runs its own independent Scraper → Assessment → Matrix pass:
      1. Scraper searches Guardian for that nation's specific query
         (e.g. "Israel United States relations")
      2. AssessmentAgent evaluates only those articles against that nation's
         three hypotheses — no cross-contamination from other nation searches
      3. MatrixAgent accumulates results into data/matrix/{nation}/
    """
    logger.info("=" * 80)
    logger.info("Starting ACH Forecasting Agent v3 — Multi-Nation")
    logger.info("=" * 80)

    try:
        nations_config = load_hypothesis_config(
            PROJECT_ROOT / "config" / "hypothesis_config.yaml"
        )
        domain_whitelist = load_domain_whitelist(
            PROJECT_ROOT / "config" / "domain_whitelist.txt"
        )

        file_manager = FileManager(settings)

        logger.info(f"Connecting to LLM at {settings.llm_endpoint}...")
        llm_interface = LLMInterface(settings)
        logger.info(f"LLM online. Model: {settings.llm_model}")

        web_scraper = WebScraper(settings, domain_whitelist)
        scraper_agent = ScraperAgent(settings, web_scraper, file_manager)

        results_by_nation: dict = {}

        for nation_id, nation_cfg in nations_config.items():
            hypotheses = nation_cfg.get("hypotheses", [])
            query = nation_cfg.get("search_query", f"{nation_id} United States")

            # Always initialise MatrixAgent first so the existing matrix_state.json
            # is loaded. This ensures the nation appears on the summary page even
            # when no new articles are found on this run.
            matrix_agent = MatrixAgent(settings, file_manager, nation_id=nation_id)

            # --- TIER 1: Scrape articles for this nation ---
            logger.info(f"[{nation_id}] TIER 1 — Scraping: {query!r}")
            articles = scraper_agent.execute(search_query=query)

            if not articles:
                logger.info(
                    f"[{nation_id}] No new articles; "
                    f"{matrix_agent.state.article_count} existing row(s) carried to summary."
                )
                matrix_agent.save_matrix()
                results_by_nation[nation_id] = matrix_agent.state
                continue

            logger.info(f"[{nation_id}] {len(articles)} new article(s) to assess")

            # --- TIER 2: Assess only this nation's articles ---
            logger.info(f"[{nation_id}] TIER 2 — Assessment ({len(hypotheses)} hypotheses)")
            assessment_agent = AssessmentAgent(settings, hypotheses, llm_interface)
            assessments = assessment_agent.execute(articles)
            flagged = sum(1 for a in assessments if a.flagged_for_human_review)
            if flagged:
                logger.warning(f"[{nation_id}] {flagged} article(s) flagged for human review")

            # --- TIER 3: Update this nation's matrix ---
            logger.info(f"[{nation_id}] TIER 3 — Matrix update")
            matrix_state = matrix_agent.execute(assessments)
            results_by_nation[nation_id] = matrix_state

            render_nation_matrix(matrix_state, nation_id)

        if not results_by_nation:
            logger.warning("No matrix state found for any nation. Exiting.")
            return

        # --- Summary page ---
        logger.info("Writing summary.html")
        summary_html = render_summary_html(results_by_nation)
        summary_path = settings.data_dir / "matrix" / "summary.html"
        summary_path.write_text(summary_html, encoding="utf-8")
        logger.info(f"Summary page written: {summary_path}")

        try:
            from rich.console import Console
            Console().print(f"\n[bold]Summary page:[/bold] {summary_path}")
        except ImportError:
            print(f"\nSummary page: {summary_path}")

        logger.info("Pipeline execution complete")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        AuditLogger.log_error("orchestrator", e)
        raise


if __name__ == "__main__":
    try:
        run_agent_pipeline()
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
