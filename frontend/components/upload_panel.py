"""
components/upload_panel.py

Lets the user point Debt Radar at a repo by uploading a .zip of the codebase.
Returns a dict describing what to scan, or None if nothing is ready yet.
Caller (app.py) is responsible for calling api_client with this.
"""

import streamlit as st


def render_upload_panel() -> dict | None:
    st.subheader("1. Point at a repo")

    uploaded = st.file_uploader(
        "Upload a .zip of your repo (include the .git folder for history analysis)",
        type=["zip"],
    )
    st.caption(
        "⚠️ Zip must include the `.git` directory or Debt Radar can only run "
        "static analysis — no commit-frequency scoring."
    )

    if uploaded is None:
        return None

    return {
        "mode": "zip",
        "zip_bytes": uploaded.getvalue(),
        "filename": uploaded.name,
    }


def render_scan_button(ready: bool) -> bool:
    """Separate so app.py can control layout (e.g. button next to a status badge)."""
    return st.button("🔍 Run Debt Radar scan", type="primary", disabled=not ready, use_container_width=True)