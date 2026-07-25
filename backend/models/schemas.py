"""
models/schemas.py
Pydantic models shared across the API, services, and core layers.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    """Input for POST /scan. Point at a local repo path the server can read."""
    repo_path: str = Field(..., description="Absolute or relative path to a git repo on disk")
    include_narration: bool = Field(
        default=True,
        description="If true, call the LLM to generate 'why this matters' blurbs for top files",
    )
    top_n: Optional[int] = Field(
        default=None,
        description="Override how many top files get narration (defaults to config.TOP_N_FOR_NARRATION)",
    )


# ---------------------------------------------------------------------------
# Static analysis primitives
# ---------------------------------------------------------------------------

class CodeSmell(BaseModel):
    """A single flagged issue inside a file."""
    type: str = Field(..., description="e.g. TODO, FIXME, LONG_FUNCTION, DEEP_NESTING")
    line: int = Field(..., description="1-indexed line number")
    detail: str = Field(..., description="Human-readable description, e.g. the comment text")


class StaticSignals(BaseModel):
    """Raw static-analysis output for one file, before scoring."""
    todo_count: int = 0
    fixme_count: int = 0
    hack_count: int = 0
    other_marker_count: int = 0
    max_function_length: int = 0
    max_nesting_depth: int = 0
    total_lines: int = 0
    smells: List[CodeSmell] = Field(default_factory=list)


class GitSignals(BaseModel):
    """Raw git-history output for one file."""
    commit_count: int = 0
    last_modified: Optional[datetime] = None
    authors: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Scored output
# ---------------------------------------------------------------------------

class FileRisk(BaseModel):
    """Fully scored risk profile for a single file, ready for the frontend."""
    file_path: str
    todo_count: int
    fixme_count: int
    hack_count: int
    max_function_length: int
    max_nesting_depth: int
    commit_frequency: int
    impact_score: float = Field(..., ge=0, le=1)
    frequency_score: float = Field(..., ge=0, le=1)
    total_score: float = Field(..., ge=0, le=1)
    smells: List[CodeSmell] = Field(default_factory=list)
    explanation: Optional[str] = Field(
        default=None, description="LLM-generated 'why this matters' narration"
    )


class ScanResponse(BaseModel):
    """Output for POST /scan."""
    repo_path: str
    scanned_at: datetime = Field(default_factory=datetime.utcnow)
    files_scanned: int
    files: List[FileRisk]


class ReportRequest(BaseModel):
    """Input for POST /report — regenerate/export a narrative summary from a prior scan."""
    scan: ScanResponse


class ReportResponse(BaseModel):
    """A single narrative report summarizing the whole scan, for the demo's headline view."""
    repo_path: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str
    top_files: List[FileRisk]
