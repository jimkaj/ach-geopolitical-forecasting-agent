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

    def save_matrix_snapshot(self, matrix_data: dict, version: str) -> Path:
        """Save a matrix snapshot.
        
        Args:
            matrix_data: Dictionary with matrix state
            version: Version string for snapshot
            
        Returns:
            Path to saved snapshot
        """
        # TODO: Implement matrix snapshot saving
        pass

    def get_directory_size_mb(self, path: Path) -> float:
        """Get total size of a directory in MB.
        
        Args:
            path: Directory path
            
        Returns:
            Size in megabytes
        """
        total_size = 0
        try:
            for file in path.rglob("*"):
                if file.is_file():
                    total_size += file.stat().st_size
        except Exception as e:
            logger.error(f"Failed to calculate directory size: {e}")
        
        return total_size / (1024 * 1024)

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

    def cleanup_old_snapshots(self, max_size_gb: float, nation_id: str = "") -> None:
        """Delete oldest snapshots if directory exceeds size limit.

        Args:
            max_size_gb: Maximum allowed size in gigabytes
            nation_id: When non-empty, prune snapshots in the nation subdirectory;
                       otherwise prune the top-level matrix directory.
        """
        target_dir = self.matrix_dir / nation_id if nation_id else self.matrix_dir
        max_size_mb = max_size_gb * 1024
        current_size_mb = self.get_directory_size_mb(target_dir)

        if current_size_mb > max_size_mb:
            logger.warning(
                f"Matrix directory {target_dir.name!r} ({current_size_mb:.2f}MB) "
                f"exceeds limit ({max_size_mb:.2f}MB). Pruning old snapshots..."
            )

            # Get all versioned snapshot files sorted by modification time.
            # `acch_matrix_v*` matches timestamped snapshots of any extension
            # (.html now, .csv historically) but not the stable acch_matrix.html
            # or matrix_state.json.
            snapshots = sorted(
                target_dir.glob("acch_matrix_v*"),
                key=lambda f: f.stat().st_mtime,
            )

            # Delete oldest files until under limit. Capture the size BEFORE
            # unlinking — stat() on a deleted file raises FileNotFoundError.
            for snapshot in snapshots:
                if current_size_mb <= max_size_mb:
                    break

                size_mb = snapshot.stat().st_size / (1024 * 1024)
                snapshot.unlink()
                current_size_mb -= size_mb
                logger.info(f"Deleted snapshot: {snapshot.name}")
