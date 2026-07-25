"""
core/git_analyzer.py
Parses `git log` once for the whole repo (not per-file — much faster) to
build a per-file commit-frequency map. Files that show up in commits most
often are treated as "hot" / high-churn, which is our proxy for risk.

Design principles
-----------------
* NEVER raise an exception that reaches the caller — if anything goes wrong
  (git not installed, .git missing/corrupt, timeout, bad output format), we
  return an empty dict and let the scorer fall back to impact-only scoring.
* Log warnings so operators can diagnose issues without exposing raw
  tracebacks to end users.
"""
from __future__ import annotations

import logging
import os
import subprocess
from collections import defaultdict
from datetime import datetime
from typing import Dict

from backend.config import GIT_LOG_SINCE_MONTHS
from backend.models.schemas import GitSignals

logger = logging.getLogger(__name__)

_COMMIT_MARKER = "__COMMIT__"


def _run_git(repo_path: str, args: list[str]) -> str:
    """
    Run a git sub-command inside *repo_path*.  Returns stdout on success,
    empty string on ANY failure (git not found, non-zero exit, timeout, etc.).
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + args,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,  # We inspect returncode ourselves
        )
        if result.returncode != 0:
            # Treat non-zero as "no output / bad repo" — log at DEBUG only
            logger.debug(
                "git exited %d for path=%s args=%s stderr=%r",
                result.returncode,
                repo_path,
                args,
                result.stderr[:200],
            )
            return ""
        return result.stdout or ""
    except FileNotFoundError:
        # `git` binary not on PATH — silently skip git analysis
        logger.warning(
            "git binary not found on PATH — commit-frequency scoring disabled."
        )
        return ""
    except subprocess.TimeoutExpired:
        logger.warning(
            "git log timed out after 30 s for path=%s — skipping git signals.",
            repo_path,
        )
        return ""
    except subprocess.SubprocessError as exc:
        logger.warning(
            "Subprocess error running git for path=%s: %s — skipping git signals.",
            repo_path,
            exc,
        )
        return ""
    except Exception as exc:
        logger.warning(
            "Unexpected error running git for path=%s: %s — skipping git signals.",
            repo_path,
            exc,
        )
        return ""


def is_git_repo(repo_path: str) -> bool:
    """
    Heuristic check: does a .git directory (or file, for worktrees) exist?
    Does NOT guarantee the repo is valid/accessible — _run_git handles that.
    """
    git_entry = os.path.join(repo_path, ".git")
    return os.path.exists(git_entry)


def analyze_repo(repo_path: str) -> Dict[str, GitSignals]:
    """
    Returns {relative_file_path: GitSignals} for every file touched in the
    last GIT_LOG_SINCE_MONTHS months.

    Returns an empty dict (never raises) when:
      - there is no .git directory
      - git is not installed
      - the repo history is empty
      - any parsing error is encountered
    """
    signals: Dict[str, GitSignals] = defaultdict(GitSignals)

    if not is_git_repo(repo_path):
        logger.info(
            "No .git directory found at %s — skipping git history analysis.",
            repo_path,
        )
        return {}

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
            "--diff-filter=d",   # exclude deleted-file entries (they can't be analysed)
        ],
    )

    if not output:
        logger.info(
            "git log returned no output for %s — empty history or error already logged.",
            repo_path,
        )
        return {}

    current_date: datetime | None = None
    current_author: str | None = None

    for line_no, raw_line in enumerate(output.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(_COMMIT_MARKER):
            # Format: __COMMIT__|<ISO8601 date>|<author name>
            parts = line.split("|", 2)
            if len(parts) != 3:
                logger.debug(
                    "Malformed commit marker at line %d (got %d parts): %r",
                    line_no,
                    len(parts),
                    line[:120],
                )
                current_date = None
                current_author = None
                continue

            _, date_str, author = parts
            try:
                current_date = datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                logger.debug("Could not parse commit date %r — treating as None.", date_str)
                current_date = None
            current_author = author or None
            continue

        # Otherwise this line is a file path touched by the current commit.
        # Skip obviously bogus lines (e.g. stray blank lines already filtered,
        # binary-diff markers, etc.)
        file_path = line
        if not file_path or file_path.startswith("Binary files"):
            continue

        try:
            sig = signals[file_path]
            sig.commit_count += 1
            if current_author and current_author not in sig.authors:
                sig.authors.append(current_author)
            if current_date and (
                sig.last_modified is None or current_date > sig.last_modified
            ):
                sig.last_modified = current_date
        except Exception as exc:
            # Per-line errors are never fatal
            logger.debug("Error recording signal for file %r: %s", file_path, exc)
            continue

    logger.info(
        "Git analysis complete for %s — %d file(s) with commit history found.",
        repo_path,
        len(signals),
    )
    return dict(signals)
