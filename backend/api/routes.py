"""
api/routes.py
Thin HTTP layer. Parses requests, calls services/scan_service.py, and
translates domain errors into HTTP status codes. No business logic here.

Endpoints
---------
POST /scan   (application/json)     – scan a repo by path already on disk
POST /scan   (multipart/form-data)  – upload a .zip, extract, then scan
POST /report                        – generate a narrative from a prior scan
GET  /health                        – liveness probe
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.models.schemas import ReportRequest, ReportResponse, ScanRequest, ScanResponse
from backend.services import scan_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_zip(zip_bytes: bytes, dest_dir: str) -> str:
    """
    Extract *zip_bytes* into *dest_dir* and return the effective repo root.

    Handles the common Windows "double-nesting" pattern where zipping a folder
    produces:  repo.zip / project / project / file.py
    We detect single-child root directories and transparently unwrap them so
    the scanner always receives the real project root.
    """
    try:
        zip_path = os.path.join(dest_dir, "_upload.zip")
        with open(zip_path, "wb") as fh:
            fh.write(zip_bytes)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Validate: reject password-protected archives early
            bad = zf.testzip()
            if bad is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Corrupt zip archive — first bad file: {bad}",
                )
            zf.extractall(dest_dir)

        os.remove(zip_path)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"Invalid zip file: {exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error extracting zip")
        raise HTTPException(
            status_code=400, detail=f"Could not extract zip archive: {exc}"
        ) from exc

    # --- Nested-root detection ---
    # Walk down as long as the current level has exactly ONE child that is a
    # directory (and no files other than hidden/system ones). This handles:
    #   dest/project/         <- single child dir, no files
    #   dest/project/project/ <- another single child dir (double-nesting)
    #   dest/project/project/src/  <- actual code starts here
    effective_root = dest_dir
    while True:
        entries = [e for e in os.listdir(effective_root) if not e.startswith(".")]
        # Filter to only non-empty entries
        dirs   = [e for e in entries if os.path.isdir(os.path.join(effective_root, e))]
        files  = [e for e in entries if os.path.isfile(os.path.join(effective_root, e))]
        if len(dirs) == 1 and len(files) == 0:
            effective_root = os.path.join(effective_root, dirs[0])
            logger.debug("Unwrapping nested root → %s", effective_root)
        else:
            break

    logger.info("Effective repo root after extraction: %s", effective_root)
    return effective_root


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=ScanResponse)
async def scan_repo(
    # JSON body fields (application/json path)
    repo_path: str | None = Form(default=None),
    include_narration: bool = Form(default=True),
    top_n: int | None = Form(default=None),
    # Optional zip upload (multipart path)
    repo_zip: UploadFile | None = File(default=None),
):
    """
    Unified scan endpoint — accepts EITHER:
      • JSON body  { repo_path, include_narration, top_n }
      • multipart  repo_zip=<file> [+ optional include_narration / top_n form fields]

    The frontend uses multipart when uploading a zip; JSON when pointing at a
    local path the backend can already access.
    """
    tmp_dir: str | None = None

    try:
        # ── ZIP UPLOAD PATH ────────────────────────────────────────────────
        if repo_zip is not None:
            filename = repo_zip.filename or "upload.zip"
            if not filename.lower().endswith(".zip"):
                raise HTTPException(
                    status_code=400,
                    detail="Only .zip archives are accepted. Please compress your repo and re-upload.",
                )

            zip_bytes = await repo_zip.read()
            if not zip_bytes:
                raise HTTPException(status_code=400, detail="Uploaded zip file is empty.")

            tmp_dir = tempfile.mkdtemp(prefix="debt_radar_")
            effective_root = _extract_zip(zip_bytes, tmp_dir)
            scan_path = effective_root

        # ── LOCAL PATH ────────────────────────────────────────────────────
        elif repo_path:
            scan_path = repo_path
        else:
            raise HTTPException(
                status_code=400,
                detail="Provide either a 'repo_path' (JSON/form) or upload a 'repo_zip' file.",
            )

        # ── RUN THE PIPELINE ──────────────────────────────────────────────
        return scan_service.run_scan(
            repo_path=scan_path,
            include_narration=include_narration,
            top_n=top_n,
        )

    except HTTPException:
        raise  # already a well-formed HTTP error — let it through

    except scan_service.RepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except scan_service.StaticAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except scan_service.LLMUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("Unhandled error in /scan")
        raise HTTPException(
            status_code=500,
            detail=f"Scan failed unexpectedly: {type(exc).__name__}: {exc}",
        ) from exc

    finally:
        # Always clean up the temp directory, even on failure
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                logger.warning("Could not remove temp dir %s", tmp_dir)


# ---------------------------------------------------------------------------
# /scan fallback: accept raw JSON body too (keeps backward-compat with tools
# that POST application/json directly instead of multipart).
# ---------------------------------------------------------------------------

@router.post("/scan/json", response_model=ScanResponse)
def scan_repo_json(request: ScanRequest) -> ScanResponse:
    """
    JSON-body variant of /scan, kept for backward compatibility and API clients
    that can't easily send multipart (e.g. curl, unit tests, other services).
    """
    try:
        return scan_service.run_scan(
            repo_path=request.repo_path,
            include_narration=request.include_narration,
            top_n=request.top_n,
        )
    except scan_service.RepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except scan_service.StaticAnalysisError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except scan_service.LLMUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unhandled error in /scan/json")
        raise HTTPException(
            status_code=500, detail=f"Scan failed: {type(exc).__name__}: {exc}"
        ) from exc


@router.post("/report", response_model=ReportResponse)
def generate_report(request: ReportRequest) -> ReportResponse:
    """
    Given a previously computed scan, produce a single narrative summary
    (used for the demo's headline / export view).
    """
    try:
        return scan_service.build_report(request.scan)
    except scan_service.LLMUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unhandled error in /report")
        raise HTTPException(
            status_code=500, detail=f"Report generation failed: {type(exc).__name__}: {exc}"
        ) from exc


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
