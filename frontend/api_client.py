"""
api_client.py

Single point of contact between the Streamlit frontend and the FastAPI backend.
No other frontend file should import `requests` directly — everything goes
through here so we have one place to change timeouts, error handling, and
the backend base URL.

Endpoint routing
----------------
scan_repo_path  → POST /scan/json  (application/json body)
scan_repo_zip   → POST /scan       (multipart/form-data with repo_zip file)
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

    Sends a JSON body to POST /scan/json.
    """
    payload = {"repo_path": repo_path, "include_narration": True}
    try:
        resp = requests.post(
            f"{_base_url()}/scan/json",
            json=payload,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ApiError(f"Could not reach backend at {_base_url()}: {e}")

    return _handle_response(resp)


def scan_repo_zip(zip_bytes: bytes, filename: str = "repo.zip") -> dict:
    """
    Kick off a scan by uploading a zipped repo. Used when the backend
    doesn't have direct filesystem access to the user's repo.

    Sends multipart/form-data to POST /scan (the zip-upload endpoint).
    """
    if not zip_bytes:
        raise ApiError("The zip file is empty — please select a valid .zip archive.")

    files = {"repo_zip": (filename, zip_bytes, "application/zip")}
    try:
        resp = requests.post(
            f"{_base_url()}/scan",
            files=files,
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.ConnectionError as e:
        raise ApiError(
            f"Could not connect to backend at {_base_url()}. "
            "Make sure FastAPI is running and the Backend URL in the sidebar is correct. "
            f"Details: {e}"
        )
    except requests.Timeout:
        raise ApiError(
            f"The backend did not respond within {DEFAULT_TIMEOUT} seconds. "
            "The repo may be very large — try increasing the timeout or scanning a smaller repo."
        )
    except requests.RequestException as e:
        raise ApiError(f"Network error communicating with backend: {e}")

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
        # Try to extract the "detail" field that FastAPI puts in error responses.
        try:
            body = resp.json()
            detail = body.get("detail") or body.get("message") or resp.text
        except ValueError:
            detail = resp.text or f"HTTP {resp.status_code}"

        # Provide human-friendly context for common status codes
        if resp.status_code == 400:
            prefix = "Bad request"
        elif resp.status_code == 404:
            prefix = "Not found"
        elif resp.status_code == 422:
            prefix = "Validation error"
        elif resp.status_code == 502:
            prefix = "LLM / upstream service error"
        elif resp.status_code == 500:
            prefix = "Internal server error"
        else:
            prefix = f"HTTP {resp.status_code}"

        raise ApiError(f"{prefix}: {detail}", resp.status_code)

    try:
        return resp.json()
    except ValueError:
        raise ApiError("Backend returned a non-JSON response.")
