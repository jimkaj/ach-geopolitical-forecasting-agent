"""Git sync helper: commit and push regenerated matrix output."""

import logging
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def sync_matrix_to_git(repo_root: Path, data_dir: Path) -> bool:
    """Commit and push data/matrix/ so GitHub Pages picks up the latest run.

    A sync failure (git missing, no network, no push credentials, etc.) is
    logged but never raised — this must not be mistaken for a pipeline failure.
    The caller must surface a False return loudly (e.g. a console warning);
    otherwise a failed push leaves GitHub Pages stale with no other signal.

    Args:
        repo_root: Git repository root (used as the subprocess cwd)
        data_dir: Settings.data_dir; data_dir/matrix is the path staged

    Returns:
        True if the push succeeded or there was nothing to sync; False if
        commit/push failed.
    """
    matrix_dir = data_dir / "matrix"
    try:
        subprocess.run(
            ["git", "add", str(matrix_dir)],
            cwd=repo_root, check=True, capture_output=True, text=True,
        )

        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_root, capture_output=True,
        )
        if diff.returncode == 0:
            logger.info("No matrix changes to commit")
            return True

        timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        subprocess.run(
            ["git", "commit", "-m", f"Update ACH matrix output: {timestamp}"],
            cwd=repo_root, check=True, capture_output=True, text=True,
        )
        subprocess.run(
            ["git", "push", "origin", "master"],
            cwd=repo_root, check=True, capture_output=True, text=True,
        )
        logger.info("Pushed matrix output to origin/master")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"Git sync failed (matrix output not pushed): {e}")
        return False
