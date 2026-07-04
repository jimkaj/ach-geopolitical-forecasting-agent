"""File management and state persistence utilities."""

import csv
import logging
from datetime import datetime
from pathlib import Path


logger = logging.getLogger(__name__)


class FileManager:
    """Manages file I/O and state persistence for the agent system."""
    
    def __init__(self, config):
        """Initialize the file manager.
        
        Args:
            config: Settings object with data directory paths
        """
        self.config = config
        self.data_dir = config.data_dir
        self.matrix_dir = self.data_dir / "matrix"
        self.processed_urls_file = self.data_dir / "processed_urls.csv"
        
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.matrix_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize processed_urls.csv if it doesn't exist
        if not self.processed_urls_file.exists():
            with open(self.processed_urls_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["url", "article_id", "processed_date"])

    def load_processed_urls(self) -> set[str]:
        """Load the set of already-processed URLs.
        
        Returns:
            Set of URLs
        """
        urls = set()
        try:
            with open(self.processed_urls_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("url"):
                        urls.add(row["url"])
            logger.info(f"Loaded {len(urls)} processed URLs")
        except Exception as e:
            logger.error(f"Failed to load processed URLs: {e}")
        
        return urls

    def record_processed_url(self, url: str, article_id: str) -> None:
        """Record that a URL has been processed.
        
        Args:
            url: The URL
            article_id: Article ID assigned to this article
        """
        try:
            with open(self.processed_urls_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([url, article_id, datetime.utcnow().isoformat()])
            logger.debug(f"Recorded processed URL: {url}")
        except Exception as e:
            logger.error(f"Failed to record processed URL: {e}")

    def get_nation_matrix_dir(self, nation_id: str) -> Path:
        """Return (and create) the per-nation matrix subdirectory.

        Args:
            nation_id: Nation identifier (e.g. "china", "russia")

        Returns:
            Path to data/matrix/{nation_id}/, created if absent
        """
        path = self.matrix_dir / nation_id
        path.mkdir(parents=True, exist_ok=True)
        return path
