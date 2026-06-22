"""
Main orchestrator for the ACH Forecasting Agent.

This is the entry point for the geopolitical forecasting system that applies
Analysis of Competing Hypotheses (ACH) to Reuters news articles.

Usage:
    python main.py
    
    This will:
    1. Load configuration from config/ and environment variables
    2. Launch three-tier agent mesh: Scraper → Assessment → Matrix
    3. Process articles in a continuous loop (interval configurable)
    4. Persist results to versioned ACH matrix snapshots
"""

import logging
import sys
from pathlib import Path

import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from agents.assessment_agent import AssessmentAgent
from agents.matrix_agent import MatrixAgent
from agents.scraper_agent import ScraperAgent
from config import settings
from tools.audit_logger import setup_audit_logging, AuditLogger
from tools.file_manager import FileManager
from tools.llm_interface import LLMInterface
from tools.web_scraper import WebScraper


# Configure logging
setup_audit_logging(settings.logs_dir)
logger = logging.getLogger(__name__)


def load_hypothesis_config(config_path: Path) -> list[dict]:
    """Load hypothesis configuration from YAML.
    
    Args:
        config_path: Path to hypothesis_config.yaml
        
    Returns:
        List of hypothesis definitions
    """
    if not config_path.exists():
        logger.error(f"Hypothesis config not found: {config_path}")
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f)
    
    hypotheses = config_data.get("hypotheses", [])
    logger.info(f"Loaded {len(hypotheses)} hypotheses from config")
    return hypotheses


def load_domain_whitelist(whitelist_path: Path) -> set[str]:
    """Load domain whitelist from text file.
    
    Args:
        whitelist_path: Path to domain_whitelist.txt
        
    Returns:
        Set of approved domains
    """
    if not whitelist_path.exists():
        logger.error(f"Domain whitelist not found: {whitelist_path}")
        raise FileNotFoundError(f"Whitelist not found: {whitelist_path}")
    
    domains = set()
    with open(whitelist_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                domains.add(line)
    
    logger.info(f"Loaded {len(domains)} whitelisted domains")
    return domains


def run_agent_pipeline() -> None:
    """Execute the three-agent pipeline: Scraper → Assessment → Matrix."""
    logger.info("=" * 80)
    logger.info("Starting ACH Forecasting Agent")
    logger.info("=" * 80)
    
    try:
        # Load configurations
        hypothesis_config = load_hypothesis_config(PROJECT_ROOT / "config" / "hypothesis_config.yaml")
        domain_whitelist = load_domain_whitelist(PROJECT_ROOT / "config" / "domain_whitelist.txt")
        
        # Initialize file manager
        file_manager = FileManager(settings)
        
        # Initialize LLM interface
        logger.info(f"Connecting to LLM at {settings.llm_endpoint}...")
        llm_interface = LLMInterface(settings)
        logger.info(f"LLM online. Model: {settings.llm_model}")
        
        # Initialize web scraper
        web_scraper = WebScraper(settings, domain_whitelist)
        
        # Initialize agents
        logger.info("Initializing agents...")
        scraper_agent = ScraperAgent(settings, web_scraper, file_manager)
        assessment_agent = AssessmentAgent(settings, hypothesis_config, llm_interface)
        matrix_agent = MatrixAgent(settings, file_manager)
        
        # --- TIER 1: Scraper Agent ---
        logger.info("TIER 1: Running Scraper Agent")
        articles = scraper_agent.execute(search_query="China US Iran conflict")
        
        if not articles:
            logger.warning("Scraper found no new articles. Exiting.")
            return
        
        logger.info(f"Scraper found {len(articles)} new articles")
        
        # --- TIER 2: Assessment Agent ---
        logger.info("TIER 2: Running Assessment Agent")
        assessments = assessment_agent.execute(articles)
        
        flagged_count = sum(1 for a in assessments if a.flagged_for_human_review)
        logger.info(f"Assessment complete. {flagged_count} articles flagged for human review.")
        
        # Log flagged articles for human review
        for assessment in assessments:
            if assessment.flagged_for_human_review:
                logger.warning(
                    f"FLAGGED FOR REVIEW: Article {assessment.article_id} "
                    f"(confidence: {assessment.overall_confidence:.2f})"
                )
        
        # --- TIER 3: Matrix Agent ---
        logger.info("TIER 3: Running Matrix Agent")
        matrix_state = matrix_agent.execute(assessments)
        
        logger.info(f"Matrix updated. Total articles processed: {matrix_state.article_count}")
        logger.info("Pipeline execution complete")
        
        # Print current matrix state
        logger.info("Current ACH Matrix State:")
        for hyp_id, agg in matrix_state.hypothesis_aggregates.items():
            logger.info(
                f"  {agg.hypothesis_name}: "
                f"++={agg.evidence_tally['++']}, "
                f"+={agg.evidence_tally['+']}, "
                f"N/A={agg.evidence_tally['N/A']}, "
                f"-={agg.evidence_tally['-']}, "
                f"--={agg.evidence_tally['--']}, "
                f"Net Support={agg.net_support:+.1f}"
            )
        
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

