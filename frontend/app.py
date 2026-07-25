"""
app.py — Debt Radar frontend entrypoint.

Flow:
  1. User points at a repo (path or zip) via upload_panel
  2. app.py calls api_client to hit the FastAPI backend's /scan endpoint
  3. Results render via results_table (ranked hotspot chart + table)
  4. Selecting a file shows its full narration via explanation_card

Run with: streamlit run app.py
"""

import streamlit as st

from api_client import ApiError, check_health, scan_repo_path, scan_repo_zip
from components.explanation_card import render_explanation_card
from components.results_table import render_results_table
from components.upload_panel import render_scan_button, render_upload_panel

st.set_page_config(
    page_title="Debt Radar",
    page_icon="🛰️",
    layout="wide",
)


def _init_state() -> None:
    if "results" not in st.session_state:
        st.session_state.results = None
    if "scan_error" not in st.session_state:
        st.session_state.scan_error = None
    if "backend_url" not in st.session_state:
        st.session_state.backend_url = "http://localhost:8000"


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Settings")
        st.session_state.backend_url = st.text_input(
            "Backend URL",
            value=st.session_state.backend_url,
            help="Where the FastAPI backend is running.",
        )

        connected = check_health()
        if connected:
            st.success("Connected to backend")
        else:
            st.error("Backend unreachable")
            st.caption("Check that FastAPI is running and the URL above is correct.")

        st.divider()
        st.caption(
            "**Debt Radar** scores files by Impact × Frequency-of-change, using "
            "git history as a signal — not just static code smells."
        )


def _run_scan(source: dict) -> None:
    st.session_state.scan_error = None
    with st.spinner("Scanning repo — parsing git history and static signals..."):
        try:
            if source["mode"] == "path":
                response = scan_repo_path(source["repo_path"])
            else:
                response = scan_repo_zip(source["zip_bytes"], source["filename"])
            st.session_state.results = response.get("files", [])
        except ApiError as e:
            st.session_state.scan_error = str(e)
            st.session_state.results = None


def main() -> None:
    _init_state()
    _render_sidebar()

    st.title("🛰️ Debt Radar")
    st.caption("Your codebase already told you what's broken — nobody was listening to git history.")

    source = render_upload_panel()
    ready = source is not None

    if render_scan_button(ready) and source:
        _run_scan(source)

    if st.session_state.scan_error:
        st.error(f"Scan failed: {st.session_state.scan_error}")

    if st.session_state.results:
        selected_file = render_results_table(st.session_state.results)
        if selected_file:
            render_explanation_card(selected_file)
        else:
            st.info("Select a file above to see the full 'why this matters' explanation.")


if __name__ == "__main__":
    main()
