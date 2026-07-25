"""
services/scan_service.py
Orchestration layer: ties together static_analyzer, git_analyzer, scorer,
and llm_client into the single flow the API routes call.
Keep this file free of FastAPI/Pydantic-request-parsing concerns — that
belongs in api/routes.py.
"""
from __future__ import annotations

import os

from backend.core import git_analyzer
from backend.config import TOP_N_FOR_NARRATION
from backend.core import static_analyzer
from backend.core.scorer import score_repo
from backend.core import llm_client
from backend.models.schemas import ReportResponse, ScanResponse


class RepoNotFoundError(Exception):
    pass


def run_scan(repo_path: str, include_narration: bool = True, top_n: int | None = None) -> ScanResponse:
    """
    Full pipeline for one repo:
      1. static_analyzer walks the tree, flags TODOs/FIXMEs and code smells
      2. git_analyzer parses commit history for churn-per-file
      3. scorer combines both into a ranked FileRisk list
      4. llm_client narrates the top N files (optional, can be skipped for speed)
    """
    if not os.path.isdir(repo_path):
        raise RepoNotFoundError(f"'{repo_path}' is not a directory the server can read")

    static_signals = static_analyzer.analyze_repo(repo_path)
    git_signals = git_analyzer.analyze_repo(repo_path)

    ranked_files = score_repo(static_signals, git_signals)

    if include_narration and ranked_files:
        n = top_n if top_n is not None else TOP_N_FOR_NARRATION
        llm_client.narrate_top_files(ranked_files, n)

    return ScanResponse(
        repo_path=repo_path,
        files_scanned=len(ranked_files),
        files=ranked_files,
    )


def build_report(scan: ScanResponse, top_n: int = TOP_N_FOR_NARRATION) -> ReportResponse:
    """Turn a completed scan into a single narrative report (headline summary + top files)."""
    summary = llm_client.summarize_scan(scan.files, scan.repo_path)
    return ReportResponse(
        repo_path=scan.repo_path,
        summary=summary,
        top_files=scan.files[:top_n],
    )
