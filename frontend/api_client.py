"""
api_client.py

Single point of contact between the Streamlit frontend and the FastAPI backend.
No other frontend file should import `requests` directly — everything goes
through here so we have one place to change timeouts, error handling, and
the backend base URL.
"""

import os
from typing import Optional

import requests

# Backend base URL — override with env var when deploying separately from backend
DEFAULT_BASE_URL = os.environ.get("DEBT_RADAR_API_URL", "http://localhost:8000")

# Static analysis + git log parsing on a real repo can take a while, LLM narration too
DEFAULT_TIMEOUT = 120


class ApiError(Exception):
    """Raised whenever the backend returns a non-2xx response or is unreachable."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _base_url() -> str:
    # Read from session_state if the user overrode it in the sidebar, else env default
    try:
        import streamlit as st

        return st.session_state.get("backend_url", DEFAULT_BASE_URL)
    except Exception:
        return DEFAULT_BASE_URL


def check_health() -> bool:
    """Quick ping so the UI can show a connected/disconnected badge."""
    try:
        resp = requests.get(f"{_base_url()}/health", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def scan_repo_path(repo_path: str) -> dict:
    """
    Kick off a scan against a repo path that's already on the machine
    the backend is running on (e.g. a mounted volume or local dev setup).
    """
    payload = {"repo_path": repo_path}
    return _post_scan(payload)


def scan_repo_zip(zip_bytes: bytes, filename: str = "repo.zip") -> dict:
    """
    Kick off a scan by uploading a zipped repo. Used when the backend
    doesn't have direct filesystem access to the user's repo.
    """
    files = {"repo_zip": (filename, zip_bytes, "application/zip")}
    try:
        resp = requests.post(f"{_base_url()}/scan", files=files, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise ApiError(f"Could not reach backend at {_base_url()}: {e}")

    return _handle_response(resp)


def _post_scan(payload: dict) -> dict:
    try:
        resp = requests.post(f"{_base_url()}/scan", json=payload, timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise ApiError(f"Could not reach backend at {_base_url()}: {e}")

    return _handle_response(resp)


def get_report(scan_id: str) -> dict:
    """
    Fetch a previously computed scan report by id, in case the backend
    caches scans instead of returning everything inline from /scan.
    """
    try:
        resp = requests.get(f"{_base_url()}/report/{scan_id}", timeout=DEFAULT_TIMEOUT)
    except requests.RequestException as e:
        raise ApiError(f"Could not reach backend at {_base_url()}: {e}")

    return _handle_response(resp)


def _handle_response(resp: requests.Response) -> dict:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(f"Backend error ({resp.status_code}): {detail}", resp.status_code)

    try:
        return resp.json()
    except ValueError:
        raise ApiError("Backend returned a non-JSON response.")
