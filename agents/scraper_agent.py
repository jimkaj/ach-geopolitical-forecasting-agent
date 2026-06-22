"""Scraper Agent: Sources geopolitical news articles via The Guardian API."""

import logging
from datetime import datetime

from tools.audit_logger import AuditLogger

from .base import ArticleData, ScraperAgentState


logger = logging.getLogger(__name__)


class ScraperAgent:
    """Tier 1 Agent: Discovers full-text geopolitical news articles.

    Responsibilities:
    - Query for articles matching geopolitical parameters (China, US, Iran)
    - Maintain long-term memory of processed URLs to avoid duplication
    - Enforce whitelist-only domain access (delegated to the WebScraper)
    - Log all scrape attempts to the audit trail
    """

    def __init__(self, config, web_scraper, file_manager):
        """Initialize the Scraper Agent.

        Args:
            config: Settings object with scraper configuration
            web_scraper: WebScraper used to query The Guardian Content API
            file_manager: FileManager owning processed-URL persistence
        """
        self.config = config
        self.web_scraper = web_scraper
        self.file_manager = file_manager
        self.state = ScraperAgentState(
            iteration_id=datetime.utcnow().isoformat(),
            articles=[],
            next_page_token=None,
            last_crawl_time=None,
            urls_processed=set(),
        )
        logger.info("ScraperAgent initialized")

    def load_processed_urls(self) -> set[str]:
        """Load the set of already-processed URLs from persistent storage.

        Returns:
            Set of URLs that have been scraped before
        """
        return self.file_manager.load_processed_urls()

    def fetch_articles(self, search_query: str) -> list[ArticleData]:
        """Fetch new articles matching the search query.

        Args:
            search_query: Search terms (e.g., "China US Iran conflict")

        Returns:
            List of ArticleData objects for new articles not previously seen

        Notes:
            - Domain whitelisting and retry/backoff are enforced by WebScraper.
            - URLs already present in processed_urls.csv are skipped, and newly
              ingested URLs are recorded so subsequent runs don't reprocess them.
        """
        raw_articles = self.web_scraper.search_articles(search_query)

        new_articles: list[ArticleData] = []
        for raw in raw_articles:
            url = raw["url"]

            if url in self.state.urls_processed:
                logger.debug(f"Skipping already-processed URL: {url}")
                continue

            try:
                article = ArticleData(
                    article_id=raw["article_id"],
                    title=raw["title"],
                    url=url,
                    content=raw["content"],
                    published_date=raw.get("published_date"),
                    source=raw.get("source", "The Guardian"),
                )
            except Exception as e:  # malformed item — log and move on
                AuditLogger.log_scrape(url, "ERROR", f"Failed to parse: {e}")
                continue

            new_articles.append(article)
            self.state.urls_processed.add(url)
            self.file_manager.record_processed_url(url, article.article_id)
            AuditLogger.log_scrape(url, "OK", article.title[:80])

        return new_articles

    def execute(self, search_query: str = "China US Iran conflict") -> list[ArticleData]:
        """Main execution method: Scrape new articles and update state.
        
        Args:
            search_query: Geopolitical search terms
            
        Returns:
            List of newly discovered articles (forwarded to Assessment Agent)
        """
        logger.info(f"ScraperAgent executing with query: {search_query}")
        
        # Load existing URLs
        existing_urls = self.load_processed_urls()
        self.state.urls_processed = existing_urls
        
        # Scrape new articles
        articles = self.fetch_articles(search_query)
        self.state.articles = articles
        self.state.last_crawl_time = datetime.utcnow()
        
        logger.info(f"ScraperAgent found {len(articles)} new articles")
        return articles
