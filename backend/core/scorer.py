"""
core/scorer.py
Combines static-analysis signals and git-history signals into a single,
ranked list of FileRisk objects.

Design:
  impact_score    = weighted blend of (todo density, function length, nesting depth), normalized 0-1
  frequency_score  = commit_count normalized against the busiest file in the repo, 0-1
  total_score      = IMPACT_ALPHA*impact + FREQUENCY_ALPHA*frequency + BOTH_BONUS*impact*frequency

The multiplicative bonus term is the whole point of this tool: a messy file
nobody touches is low priority; a messy file that's under constant repair is
the one to fix first.
"""
from __future__ import annotations

from typing import Dict, List

from backend.config import (
    BOTH_BONUS,
    FREQUENCY_ALPHA,
    IMPACT_ALPHA,
    IMPACT_WEIGHTS,
    MAX_FUNCTION_LENGTH,
    MAX_NESTING_DEPTH,
)
from backend.models.schemas import FileRisk, GitSignals, StaticSignals


def _normalize(value: float, max_value: float) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


def _impact_score(signals: StaticSignals) -> float:
    """Blend TODO density, function length, and nesting into one 0-1 impact number."""
    total_markers = signals.todo_count + signals.fixme_count + signals.hack_count
    # Weight FIXME/HACK more heavily than plain TODO by counting them extra.
    weighted_markers = signals.todo_count * 1.0 + signals.fixme_count * 2.0 + signals.hack_count * 1.5
    lines = max(signals.total_lines, 1)
    todo_density = _normalize(weighted_markers / lines * 100, 5.0)  # ~5 weighted markers per 100 lines = max

    function_length_score = _normalize(signals.max_function_length, MAX_FUNCTION_LENGTH * 3)
    nesting_score = _normalize(signals.max_nesting_depth, MAX_NESTING_DEPTH * 2)

    score = (
        IMPACT_WEIGHTS["todo_density"] * todo_density
        + IMPACT_WEIGHTS["function_length"] * function_length_score
        + IMPACT_WEIGHTS["nesting_depth"] * nesting_score
    )
    return round(max(0.0, min(1.0, score)), 4)


def score_repo(
    static_signals: Dict[str, StaticSignals],
    git_signals: Dict[str, GitSignals],
) -> List[FileRisk]:
    """Combine static + git signals per file and return them ranked by total_score desc."""
    max_commits = max((s.commit_count for s in git_signals.values()), default=0)

    results: List[FileRisk] = []
    for rel_path, static in static_signals.items():
        git = git_signals.get(rel_path, GitSignals())

        impact = _impact_score(static)
        frequency = round(_normalize(git.commit_count, max_commits), 4) if max_commits else 0.0

        total = round(
            IMPACT_ALPHA * impact + FREQUENCY_ALPHA * frequency + BOTH_BONUS * impact * frequency,
            4,
        )

        results.append(
            FileRisk(
                file_path=rel_path,
                todo_count=static.todo_count,
                fixme_count=static.fixme_count,
                hack_count=static.hack_count,
                max_function_length=static.max_function_length,
                max_nesting_depth=static.max_nesting_depth,
                commit_frequency=git.commit_count,
                impact_score=impact,
                frequency_score=frequency,
                total_score=total,
                smells=static.smells,
            )
        )

    results.sort(key=lambda f: f.total_score, reverse=True)
    return results
