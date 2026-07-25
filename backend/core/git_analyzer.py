"""
core/git_analyzer.py
Parses `git log` once for the whole repo (not per-file — much faster) to
build a per-file commit-frequency map. Files that show up in commits most
often are treated as "hot" / high-churn, which is our proxy for risk.
"""
from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import Dict

from backend.config import GIT_LOG_SINCE_MONTHS
from backend.models.schemas import GitSignals

_COMMIT_MARKER = "__COMMIT__"


def _run_git(repo_path: str, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + args,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return result.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def is_git_repo(repo_path: str) -> bool:
    return os.path.isdir(os.path.join(repo_path, ".git"))


def analyze_repo(repo_path: str) -> Dict[str, GitSignals]:
    """
    Returns {relative_file_path: GitSignals} for every file touched in the
    last GIT_LOG_SINCE_MONTHS months. Files never committed (or not in git)
    simply won't appear and get a default (zero) frequency downstream.
    """
    signals: Dict[str, GitSignals] = defaultdict(GitSignals)

    if not is_git_repo(repo_path):
        return signals

    # One log call for the whole repo: each commit prints a marker line with
    # its ISO date + author, followed by the list of files it touched.
    log_format = f"{_COMMIT_MARKER}|%aI|%an"
    output = _run_git(
        repo_path,
        [
            "log",
            f"--since={GIT_LOG_SINCE_MONTHS}.months.ago",
            f"--pretty=format:{log_format}",
            "--name-only",
        ],
    )

    if not output:
        return signals

    current_date: datetime | None = None
    current_author: str | None = None

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(_COMMIT_MARKER):
            _, date_str, author = line.split("|", 2)
            try:
                current_date = datetime.fromisoformat(date_str)
            except ValueError:
                current_date = None
            current_author = author
            continue

        # Otherwise this line is a file path touched by current_date/current_author's commit.
        file_path = line
        sig = signals[file_path]
        sig.commit_count += 1
        if current_author and current_author not in sig.authors:
            sig.authors.append(current_author)
        if current_date and (sig.last_modified is None or current_date > sig.last_modified):
            sig.last_modified = current_date

    return dict(signals)
