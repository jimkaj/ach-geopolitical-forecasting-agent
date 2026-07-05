"""Tests for the git sync helper (no real git/network calls)."""

import subprocess
from unittest.mock import MagicMock, patch

from tools.git_sync import sync_matrix_to_git


def _run_side_effect(diff_returncode):
    """Build a subprocess.run stub: real calls succeed except the diff check."""

    def _run(cmd, **kwargs):
        if cmd[:3] == ["git", "diff", "--cached"]:
            return MagicMock(returncode=diff_returncode)
        return MagicMock(returncode=0)

    return _run


@patch("tools.git_sync.subprocess.run")
def test_stages_commits_and_pushes_when_changes_exist(mock_run, tmp_path):
    mock_run.side_effect = _run_side_effect(diff_returncode=1)

    sync_matrix_to_git(tmp_path, tmp_path / "data")

    commands = [call.args[0] for call in mock_run.call_args_list]
    assert commands[0][:2] == ["git", "add"]
    assert commands[1][:3] == ["git", "diff", "--cached"]
    assert commands[2][:2] == ["git", "commit"]
    assert commands[3] == ["git", "push", "origin", "master"]


@patch("tools.git_sync.subprocess.run")
def test_skips_commit_and_push_when_nothing_staged(mock_run, tmp_path):
    mock_run.side_effect = _run_side_effect(diff_returncode=0)

    sync_matrix_to_git(tmp_path, tmp_path / "data")

    commands = [call.args[0] for call in mock_run.call_args_list]
    assert len(commands) == 2  # add + diff only
    assert not any(cmd[:2] == ["git", "commit"] for cmd in commands)
    assert not any(cmd[:2] == ["git", "push"] for cmd in commands)


@patch("tools.git_sync.subprocess.run")
def test_git_failure_is_caught_not_raised(mock_run, tmp_path):
    mock_run.side_effect = subprocess.CalledProcessError(1, ["git", "add"])

    sync_matrix_to_git(tmp_path, tmp_path / "data")  # must not raise


@patch("tools.git_sync.subprocess.run")
def test_missing_git_binary_is_caught_not_raised(mock_run, tmp_path):
    mock_run.side_effect = FileNotFoundError("git not found")

    sync_matrix_to_git(tmp_path, tmp_path / "data")  # must not raise
