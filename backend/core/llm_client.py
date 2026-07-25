"""
core/llm_client.py
Thin wrapper around the Gemini API. Its ONLY job is narration: turning
already-computed ranked signals into a short, plain-English "why this
matters" blurb. It does no analysis or scoring of its own.

If GEMINI_API_KEY isn't set, falls back to a templated explanation so the
rest of the app still works (useful for offline demos).
"""
from __future__ import annotations

from typing import List

from backend.config import LLM_ENABLED, LLM_MAX_TOKENS, LLM_MODEL
from backend.models.schemas import FileRisk

_SYSTEM_PROMPT = (
    "You are a senior engineer writing terse, concrete explanations for a "
    "technical-debt dashboard. Given signals about a file (TODO/FIXME counts, "
    "longest function, nesting depth, and how often it's been committed to "
    "recently), write 2-3 sentences explaining WHY this file is risky and "
    "what to fix first. Be specific and reference the actual numbers given. "
    "No fluff, no generic advice, no markdown headers. Plain sentences only."
)


def _fallback_explanation(file_risk: FileRisk) -> str:
    """Deterministic, no-LLM explanation used when narration is disabled or fails."""
    parts = []
    if file_risk.fixme_count or file_risk.hack_count:
        parts.append(
            f"{file_risk.fixme_count} FIXME(s) and {file_risk.hack_count} HACK(s) flag known problems"
        )
    elif file_risk.todo_count:
        parts.append(f"{file_risk.todo_count} open TODO(s)")
    if file_risk.max_function_length:
        parts.append(f"a {file_risk.max_function_length}-line function")
    if file_risk.max_nesting_depth:
        parts.append(f"{file_risk.max_nesting_depth} levels of nesting")
    signal_text = ", ".join(parts) if parts else "elevated complexity"

    churn_text = (
        f"it's been committed to {file_risk.commit_frequency} times recently"
        if file_risk.commit_frequency
        else "it hasn't changed recently"
    )

    return (
        f"This file has {signal_text}, and {churn_text}. "
        f"Combined risk score: {file_risk.total_score:.2f}/1.0 — "
        f"prioritize this over files with lower churn even if they look messier."
    )


def _build_client():
    """Lazily import + construct the Gemini client so the module import
    never fails just because the SDK/key isn't available."""
    from google import genai
    from backend.config import GEMINI_API_KEY

    return genai.Client(api_key=GEMINI_API_KEY)


def narrate_file(file_risk: FileRisk) -> str:
    """Generate (or fall back to) a 'why this matters' explanation for one file."""
    if not LLM_ENABLED:
        return _fallback_explanation(file_risk)

    smell_lines = "\n".join(
        f"- line {s.line}: [{s.type}] {s.detail}" for s in file_risk.smells[:10]
    )
    user_prompt = (
        f"File: {file_risk.file_path}\n"
        f"TODOs: {file_risk.todo_count}, FIXMEs: {file_risk.fixme_count}, HACKs: {file_risk.hack_count}\n"
        f"Longest function: {file_risk.max_function_length} lines\n"
        f"Deepest nesting: {file_risk.max_nesting_depth} levels\n"
        f"Commits touching this file recently: {file_risk.commit_frequency}\n"
        f"Impact score: {file_risk.impact_score}, Frequency score: {file_risk.frequency_score}, "
        f"Total risk score: {file_risk.total_score}\n"
        f"Flagged issues:\n{smell_lines if smell_lines else '(none listed)'}\n\n"
        "Explain why this file is risky and what to fix first."
    )

    try:
        client = _build_client()
        from google.genai import types
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=LLM_MAX_TOKENS,
            )
        )
        return (response.text.strip() if response.text else "") or _fallback_explanation(file_risk)
    except Exception:
        # Never let a narration failure break the scan — degrade gracefully.
        return _fallback_explanation(file_risk)


def narrate_top_files(ranked_files: List[FileRisk], top_n: int) -> List[FileRisk]:
    """Mutates and returns the list, filling `.explanation` for the top N files only
    (narration is the expensive step, so we don't run it for every file in the repo)."""
    for file_risk in ranked_files[:top_n]:
        file_risk.explanation = narrate_file(file_risk)
    return ranked_files


def summarize_scan(ranked_files: List[FileRisk], repo_path: str) -> str:
    """One-paragraph headline summary for the /report endpoint."""
    if not ranked_files:
        return "No scannable files were found in this repository."

    top = ranked_files[0]
    if not LLM_ENABLED:
        return (
            f"Scanned {repo_path}. The highest-risk file is {top.file_path} "
            f"with a total score of {top.total_score:.2f}/1.0, driven by "
            f"{top.todo_count + top.fixme_count + top.hack_count} open comment markers "
            f"and {top.commit_frequency} recent commits. Review the top-ranked files below."
        )

    file_lines = "\n".join(
        f"- {f.file_path}: score {f.total_score}, {f.todo_count + f.fixme_count + f.hack_count} markers, "
        f"{f.commit_frequency} recent commits"
        for f in ranked_files[:10]
    )
    user_prompt = (
        f"Repo: {repo_path}\nTop-ranked risky files:\n{file_lines}\n\n"
        "Write a 3-4 sentence executive summary of the codebase's technical debt "
        "hotspots for a team lead deciding what to prioritize next sprint."
    )

    try:
        client = _build_client()
        from google.genai import types
        response = client.models.generate_content(
            model=LLM_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=LLM_MAX_TOKENS,
            )
        )
        return response.text.strip() if response.text else ""
    except Exception:
        return (
            f"Scanned {repo_path}. The highest-risk file is {top.file_path} "
            f"with a total score of {top.total_score:.2f}/1.0."
        )