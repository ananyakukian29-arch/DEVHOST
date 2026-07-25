"""
components/upload_panel.py

Lets the user point Debt Radar at a repo either by:
  1. Typing a local path (fast for the demo — point at a repo already
     cloned next to the backend), or
  2. Uploading a .zip of the repo (works when frontend/backend run on
     different machines, e.g. a hosted demo).

Returns a dict describing what to scan, or None if nothing is ready yet.
Caller (app.py) is responsible for calling api_client with this.
"""

import streamlit as st


def render_upload_panel() -> dict | None:
    st.subheader("1. Point at a repo")

    mode = st.radio(
        "How do you want to provide the repo?",
        options=["Local path", "Upload .zip"],
        horizontal=True,
        help="Local path is fastest if the backend can already see your filesystem.",
    )

    if mode == "Local path":
        repo_path = st.text_input(
            "Path to repo on the backend's machine",
            placeholder="/home/user/projects/my-repo",
        )
        st.caption("The FastAPI backend will read git history and files directly from this path.")

        if not repo_path:
            return None

        return {"mode": "path", "repo_path": repo_path}

    else:
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
