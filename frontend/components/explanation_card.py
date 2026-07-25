"""
components/explanation_card.py

Renders the detail view for a single file: its raw signals plus the
LLM-generated plain-English "why this matters" blurb. This is what makes
Debt Radar feel different from a linter dump — the narration is the
selling point, so give it visual weight.
"""

import streamlit as st

from utils.formatting import (
    format_commit_frequency,
    format_score,
    score_to_badge,
    score_to_color,
)


def render_explanation_card(file_risk: dict) -> None:
    if not file_risk:
        return

    st.subheader("3. Why this matters")

    file_path = file_risk.get("file_path", "Unknown file")
    score = file_risk.get("score", 0)
    color = score_to_color(score)
    badge = score_to_badge(score)
    explanation = file_risk.get(
        "explanation",
        "No narration available for this file yet — the LLM explanation step may have "
        "been skipped or failed for this file.",
    )

    st.markdown(
        f"""
<div style="border-left: 6px solid {color}; padding: 0.75rem 1rem; border-radius: 6px;
            background-color: rgba(128,128,128,0.08);">
  <div style="display:flex; justify-content: space-between; align-items:center;">
    <code style="font-size: 0.95rem;">{file_path}</code>
    <span style="font-weight:600;">{badge} · {format_score(score)}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(f"> {explanation}")

    st.markdown("**Signals behind this score**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TODO / FIXME / HACK", _todo_total(file_risk))
    c2.metric("Longest function", f"{file_risk.get('max_function_length', '—')} lines")
    c3.metric("Max nesting depth", file_risk.get("max_nesting_depth", "—"))
    c4.metric("Commits (90d)", file_risk.get("commits_last_90_days", "—"))

    st.caption(format_commit_frequency(file_risk.get("commits_last_90_days", 0)))

    with st.expander("Raw signal breakdown"):
        st.json(
            {
                "impact_score": file_risk.get("impact"),
                "frequency_score": file_risk.get("frequency"),
                "final_score": score,
                "todo_count": file_risk.get("todo_count"),
                "fixme_count": file_risk.get("fixme_count"),
                "hack_count": file_risk.get("hack_count"),
            }
        )


def _todo_total(file_risk: dict) -> int:
    return (
        file_risk.get("todo_count", 0)
        + file_risk.get("fixme_count", 0)
        + file_risk.get("hack_count", 0)
    )
