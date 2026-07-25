"""
services/scan_service.py
Orchestration layer: ties together static_analyzer, git_analyzer, scorer,
and llm_client into the single flow the API routes call.
Keep this file free of FastAPI/Pydantic-request-parsing concerns — that
belongs in api/routes.py.
"""
from __future__ import annotations

import logging
import os

from backend.core import git_analyzer
from backend.config import TOP_N_FOR_NARRATION
from backend.core import static_analyzer
from backend.core.scorer import score_repo
from backend.core import llm_client
from backend.models.schemas import ReportResponse, ScanResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions — routes.py maps these to HTTP status codes
# ---------------------------------------------------------------------------

class RepoNotFoundError(Exception):
    """Raised when the repo path does not exist or is not a directory."""


class StaticAnalysisError(Exception):
    """Raised when static analysis fails in a non-recoverable way (e.g. permission denied)."""


class LLMUnavailableError(Exception):
    """Raised when the LLM is configured but its API is unreachable/rejected the request."""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_scan(
    repo_path: str,
    include_narration: bool = True,
    top_n: int | None = None,
) -> ScanResponse:
    """
    Full pipeline for one repo:
      1. static_analyzer walks the tree, flags TODOs/FIXMEs and code smells
      2. git_analyzer parses commit history for churn-per-file
         (skipped gracefully if .git is absent / git binary missing)
      3. scorer combines both into a ranked FileRisk list
      4. llm_client narrates the top N files (optional, degrades gracefully)
    """
    if not os.path.isdir(repo_path):
        raise RepoNotFoundError(
            f"'{repo_path}' is not a directory the server can read. "
            "Check the path or re-upload the zip."
        )

    # ── Stage 1: Static analysis ───────────────────────────────────────────
    try:
        static_signals = static_analyzer.analyze_repo(repo_path)
    except PermissionError as exc:
        raise StaticAnalysisError(
            f"The server cannot read files under '{repo_path}': {exc}"
        ) from exc
    except Exception as exc:
        logger.exception("Static analysis failed for %s", repo_path)
        raise StaticAnalysisError(
            f"Static analysis encountered an unexpected error: {type(exc).__name__}: {exc}"
        ) from exc

    if not static_signals:
        raise StaticAnalysisError(
            "No supported source files were found in this repository. "
            "Ensure the zip contains at least one .py / .js / .ts / .go / .java / .rb / .c / .cpp / .cs file."
        )

    # ── Stage 2: Git history (best-effort — never crashes the scan) ────────
    git_signals: dict = {}
    try:
        git_signals = git_analyzer.analyze_repo(repo_path)
        if not git_signals:
            logger.info(
                "No git signals for %s — either no .git dir, empty history, "
                "or git is not installed. Falling back to static-only scoring.",
                repo_path,
            )
    except Exception as exc:
        # Git errors are NEVER fatal. Log and continue with zero git signals.
        logger.warning(
            "Git analysis failed for %s (%s: %s). "
            "Commit-frequency scoring disabled — using static analysis only.",
            repo_path,
            type(exc).__name__,
            exc,
        )
        git_signals = {}

    # ── Stage 3: Score + rank ─────────────────────────────────────────────
    try:
        ranked_files = score_repo(static_signals, git_signals)
    except Exception as exc:
        logger.exception("Scoring failed for %s", repo_path)
        raise StaticAnalysisError(
            f"Scoring pipeline failed: {type(exc).__name__}: {exc}"
        ) from exc

    # ── Stage 4: LLM narration (optional, always degrades gracefully) ──────
    if include_narration and ranked_files:
        n = top_n if top_n is not None else TOP_N_FOR_NARRATION
        try:
            llm_client.narrate_top_files(ranked_files, n)
        except Exception as exc:
            # narrate_top_files itself already catches per-file errors and uses
            # _fallback_explanation, so we should never reach here. Belt-and-
            # suspenders: log and continue without narration rather than crash.
            logger.warning(
                "LLM narration raised an unexpected top-level error (%s: %s). "
                "Continuing without narration.",
                type(exc).__name__,
                exc,
            )

    return ScanResponse(
        repo_path=repo_path,
        files_scanned=len(ranked_files),
        files=ranked_files,
    )


def build_report(scan: ScanResponse, top_n: int = TOP_N_FOR_NARRATION) -> ReportResponse:
    """Turn a completed scan into a single narrative report (headline summary + top files)."""
    try:
        summary = llm_client.summarize_scan(scan.files, scan.repo_path)
    except Exception as exc:
        logger.warning(
            "summarize_scan raised an unexpected error (%s: %s). Using fallback summary.",
            type(exc).__name__,
            exc,
        )
        summary = _fallback_summary(scan)

    # Guard against empty string from a failed LLM call
    if not summary:
        summary = _fallback_summary(scan)

    return ReportResponse(
        repo_path=scan.repo_path,
        summary=summary,
        top_files=scan.files[:top_n],
    )


def _fallback_summary(scan: ScanResponse) -> str:
    """Deterministic summary used when the LLM is unavailable."""
    if not scan.files:
        return "No scannable files were found in this repository."
    top = scan.files[0]
    return (
        f"Scanned {scan.repo_path}: {scan.files_scanned} file(s) analysed. "
        f"Highest-risk file is '{top.file_path}' "
        f"(total score {top.total_score:.2f}/1.0, "
        f"{top.todo_count + top.fixme_count + top.hack_count} comment markers, "
        f"{top.commit_frequency} recent commits). "
        "Review the ranked list below to prioritise refactoring."
    )
