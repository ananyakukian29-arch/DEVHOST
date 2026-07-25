"""
api/routes.py
Thin HTTP layer. Parses requests, calls services/scan_service.py, and
translates domain errors into HTTP status codes. No business logic here.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models.schemas import ReportRequest, ReportResponse, ScanRequest, ScanResponse
from backend.services import scan_service

router = APIRouter()


@router.post("/scan", response_model=ScanResponse)
def scan_repo(request: ScanRequest) -> ScanResponse:
    """
    Run the full Debt Radar pipeline against a repo on disk:
    static analysis + git history -> scored, ranked list of risky files.
    """
    try:
        return scan_service.run_scan(
            repo_path=request.repo_path,
            include_narration=request.include_narration,
            top_n=request.top_n,
        )
    except scan_service.RepoNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:  # pragma: no cover - safety net for the demo
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}") from e


@router.post("/report", response_model=ReportResponse)
def generate_report(request: ReportRequest) -> ReportResponse:
    """
    Given a previously computed scan, produce a single narrative summary
    (used for the demo's headline / export view).
    """
    try:
        return scan_service.build_report(request.scan)
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Report generation failed: {e}") from e


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
