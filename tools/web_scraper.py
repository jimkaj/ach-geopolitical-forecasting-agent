"""Article sourcing via The Guardian Open Platform Content API.

reuters.com is not crawled directly (ToS, bot mitigation, dead legacy RSS) and
its full text is licensed-only. The Guardian, by contrast, exposes an official
developer Content API that returns the *full article body* with a free key, so
we use it as the article source. See https://open-platform.theguardian.com/.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import requests


logger = logging.getLogger(__name__)

# A browser-like User-Agent (harmless for the API; kept for consistency).
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class WebScraper:
    """Fetches full-text news articles from The Guardian Content API.

    Queries `content.guardianapis.com/search` with `show-fields=bodyText` so
    each result carries the complete article body. Requires an API key
    (`config.guardian_api_key`); the literal "test" key works for development.
    """

    def __init__(self, config, domain_whitelist: set[str]):
        """Initialize the web scraper.

        Args:
            config: Settings object with scraper configuration
            domain_whitelist: Set of approved domains
        """
        self.config = config
        self.domain_whitelist = domain_whitelist

        # Behind a TLS-inspecting proxy, the proxy's CA lives in the OS trust
        # store but not in certifi's bundle, so verification fails. Routing TLS
        # through the OS trust store fixes this while keeping verification on.
        if getattr(config, "use_system_truststore", False):
            try:
                import truststore

                truststore.inject_into_ssl()
                logger.debug("Injected system trust store for TLS verification")
            except ImportError:
                logger.warning(
                    "use_system_truststore is set but the 'truststore' package "
                    "is not installed; falling back to certifi defaults"
                )

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _USER_AGENT})

    def _is_domain_allowed(self, url: str) -> bool:
        """Check if a URL's domain is in the whitelist.

        Args:
            url: URL to check

        Returns:
            True if domain is whitelisted
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix for comparison
        domain_clean = domain.replace("www.", "")

        for allowed in self.domain_whitelist:
            if domain_clean == allowed.lower() or domain_clean.endswith("." + allowed.lower()):
                return True

        return False

    def fetch_with_retries(
        self, url: str, params: Optional[dict] = None
    ) -> Optional[requests.Response]:
        """Fetch a URL with exponential backoff retry logic.

        Args:
            url: URL to fetch (the base URL; query params go in ``params``)
            params: Query parameters. Kept separate from ``url`` so secrets
                (e.g. the API key) are never written to the logs.

        Returns:
            Response object or None if all retries failed
        """
        if not self._is_domain_allowed(url):
            logger.warning(f"Domain not whitelisted: {url}")
            return None

        for attempt in range(self.config.scraper_max_retries):
            try:
                response = self.session.get(
                    url, params=params, timeout=self.config.scraper_timeout_seconds
                )
                response.raise_for_status()
                logger.info(f"Successfully fetched {url}")
                return response
            except requests.exceptions.RequestException:
                wait_time = self.config.scraper_backoff_factor ** attempt
                logger.warning(
                    f"Attempt {attempt + 1}/{self.config.scraper_max_retries} failed for {url}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)

        logger.error(f"Failed to fetch {url} after {self.config.scraper_max_retries} attempts")
        return None

    def _recent_from_date(self) -> Optional[str]:
        """Compute the Guardian ``from-date`` for the configured recency window.

        Returns:
            An ISO date string (YYYY-MM-DD) N days ago, or None to not filter.
        """
        days = getattr(self.config, "guardian_from_days", 0)
        if not days or days <= 0:
            return None
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return cutoff.date().isoformat()

    def _parse_guardian_result(self, result: dict) -> Optional[dict]:
        """Convert a single Guardian API result into an article dict.

        Args:
            result: One entry from ``response.results`` in the API payload

        Returns:
            Dict with article_id, title, url, content, published_date, source —
            or None if the result lacks a web URL (needed for deduplication).
        """
        web_url = (result.get("webUrl") or "").strip()
        if not web_url:
            return None

        fields = result.get("fields") or {}
        title = (fields.get("headline") or result.get("webTitle") or "").strip()

        # bodyText is the full article body as plain text (no HTML). Fall back
        # to the title so content is never empty (e.g. for the odd liveblog).
        body = (fields.get("bodyText") or "").strip()
        content = body or title

        published_date = None
        raw_date = result.get("webPublicationDate")
        if raw_date:
            try:
                published_date = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
            except ValueError:
                logger.debug(f"Unparseable webPublicationDate: {raw_date!r}")

        # The Guardian `id` (e.g. "world/2026/may/15/slug") is stable and unique.
        article_id = result.get("id") or web_url

        return {
            "article_id": article_id,
            "title": title,
            "url": web_url,
            "content": content,
            "published_date": published_date,
            "source": "The Guardian",
        }

    def fetch_article_by_id(self, article_id: str) -> Optional[dict]:
        """Re-fetch one article's full body by its Guardian content ID.

        Used to re-score an already-ingested article against a different LLM,
        bypassing the search endpoint (which only returns current top-N
        results within a recency window, not a stable historical set).

        Args:
            article_id: Guardian content ID (e.g. "world/2026/jun/27/slug"),
                as stored in EvidenceRow.article_id.

        Returns:
            Article dict (see :meth:`_parse_guardian_result`), or None on
            fetch/parse/status failure.
        """
        base = self.config.guardian_api_url.rsplit("/", 1)[0]
        item_url = f"{base}/{article_id}"
        params = {"show-fields": "bodyText,headline,byline", "api-key": self.config.guardian_api_key}

        response = self.fetch_with_retries(item_url, params=params)
        if response is None:
            logger.error(f"Failed to re-fetch article by id: {article_id}")
            return None

        try:
            payload = response.json().get("response", {})
        except ValueError as e:
            logger.error(f"Failed to parse Guardian JSON response for {article_id}: {e}")
            return None

        if payload.get("status") != "ok":
            logger.error(f"Guardian API returned status {payload.get('status')!r} for {article_id}")
            return None

        return self._parse_guardian_result(payload.get("content", {}))

    def search_articles(self, search_query: str) -> list[dict]:
        """Search The Guardian Content API for full-text articles.

        Args:
            search_query: Search terms (e.g. "China US Iran conflict")

        Returns:
            List of article dicts (see :meth:`_parse_guardian_result`), capped at
            ``config.scraper_max_articles``. Empty list on fetch/parse failure.
        """
        params = {
            "q": search_query,
            "show-fields": "bodyText,headline,byline",
            "order-by": self.config.guardian_order_by,
            "page-size": min(self.config.scraper_max_articles, 200),
            "api-key": self.config.guardian_api_key,
        }
        if self.config.guardian_section:
            params["section"] = self.config.guardian_section
        from_date = self._recent_from_date()
        if from_date:
            params["from-date"] = from_date

        logger.info(f"Searching Guardian Content API for: {search_query!r}")
        response = self.fetch_with_retries(self.config.guardian_api_url, params=params)
        if response is None:
            logger.error("Guardian API fetch failed; returning no articles")
            return []

        try:
            payload = response.json().get("response", {})
        except ValueError as e:
            logger.error(f"Failed to parse Guardian JSON response: {e}")
            return []

        if payload.get("status") != "ok":
            logger.error(f"Guardian API returned status: {payload.get('status')!r}")
            return []

        articles: list[dict] = []
        for result in payload.get("results", []):
            parsed = self._parse_guardian_result(result)
            if parsed is not None:
                articles.append(parsed)
            if len(articles) >= self.config.scraper_max_articles:
                break

        logger.info(f"Guardian API returned {len(articles)} article(s)")
        return articles
