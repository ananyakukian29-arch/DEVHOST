"""
components/results_table.py

Renders the ranked list of risky files returned by /scan. This is the
main demo payoff screen, so it leads with a bar chart (visual, scans well
on a projector) then a sortable table underneath.

Expects `results` to be a list of dicts shaped like the backend's
FileRisk schema, e.g.:
    {
        "file_path": "src/payments/charge.py",
        "score": 87.3,
        "impact": 74.0,
        "frequency": 0.92,
        "todo_count": 3,
        "fixme_count": 1,
        "hack_count": 0,
        "max_function_length": 142,
        "max_nesting_depth": 6,
        "commits_last_90_days": 21,
        "explanation": "This file changes almost weekly and still carries...",
    }
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.formatting import format_score, score_to_badge, score_to_color, truncate_path


def render_results_table(results: list) -> dict | None:
    """
    Renders the hotspot chart + table.
    Returns the selected file's risk dict (for the explanation card),
    or None if nothing is selected yet.
    """
    if not results:
        st.info("No results yet — run a scan to see your hotspot list.")
        return None

    st.subheader("2. Ranked hotspots")

    df = pd.DataFrame(results).sort_values("total_score", ascending=False).reset_index(drop=True)
    df["display_path"] = df["file_path"].apply(truncate_path)
    df["badge"] = df["total_score"].apply(score_to_badge)
    df["color"] = df["total_score"].apply(score_to_color)

    top_n = st.slider("Show top N files", min_value=5, max_value=min(50, len(df)), value=min(10, len(df)))
    top_df = df.head(top_n)

    _render_chart(top_df)
    selected_path = _render_table(top_df)

    if selected_path:
        match = df[df["file_path"] == selected_path]
        if not match.empty:
            return match.iloc[0].to_dict()

    return None


def _render_chart(df: pd.DataFrame) -> None:
    fig = px.bar(
        df.sort_values("total_score"),
        x="total_score",
        y="display_path",
        orientation="h",
        color="total_score",
        color_continuous_scale=["#3DAA5C", "#F5A623", "#E5484D"],
        labels={"total_score": "Risk score", "display_path": "File"},
        height=max(300, 34 * len(df)),
    )
    fig.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_table(df: pd.DataFrame) -> str | None:
    display_cols = {
        "display_path": "File",
        "badge": "Risk",
        "total_score": "Score",
        "todo_count": "TODOs",
        "fixme_count": "FIXMEs",
        "commit_frequency": "Commits (recent)",
        "max_function_length": "Longest fn (lines)",
    }
    available_cols = [c for c in display_cols if c in df.columns]
    table_df = df[available_cols].rename(columns=display_cols)
    table_df["Score"] = df["total_score"].apply(format_score)

    event = st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        return df.iloc[selected_rows[0]]["file_path"]

    # Fallback selector for older Streamlit versions without dataframe selection events
    st.caption("Or pick a file to see the full explanation:")
    choice = st.selectbox(
        "Select a file",
        options=["—"] + df["file_path"].tolist(),
        label_visibility="collapsed",
    )
    return None if choice == "—" else choice
