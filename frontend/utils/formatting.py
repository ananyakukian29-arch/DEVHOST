"""
utils/formatting.py

Pure functions that turn a raw risk score into something visual: a color,
a badge label, an emoji. Kept separate from components so the thresholds
live in exactly one place and are easy to tune during the demo.
"""

from typing import Tuple

# Score is assumed to be normalized 0-100 by the backend scorer.
# Tune these during rehearsal to match whatever repo you're demoing on.
HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40


def risk_tier(score: float) -> str:
    """Returns 'high', 'medium', or 'low' for a given 0-100 score."""
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= MEDIUM_RISK_THRESHOLD:
        return "medium"
    return "low"


def score_to_color(score: float) -> str:
    """Hex color for charts/badges, red=risky, green=safe."""
    tier = risk_tier(score)
    return {
        "high": "#E5484D",    # red
        "medium": "#F5A623",  # amber
        "low": "#3DAA5C",     # green
    }[tier]


def score_to_badge(score: float) -> str:
    """Emoji + label combo for quick scanning in a table or card."""
    tier = risk_tier(score)
    return {
        "high": "🔥 High risk",
        "medium": "⚠️ Medium risk",
        "low": "✅ Low risk",
    }[tier]


def score_to_emoji(score: float) -> str:
    tier = risk_tier(score)
    return {"high": "🔥", "medium": "⚠️", "low": "✅"}[tier]


def format_score(score: float) -> str:
    """Consistent one-decimal display, e.g. 87.3"""
    return f"{score:.1f}"


def format_commit_frequency(commits_last_90_days: int) -> str:
    if commits_last_90_days == 0:
        return "No recent changes"
    if commits_last_90_days == 1:
        return "1 commit in last 90 days"
    return f"{commits_last_90_days} commits in last 90 days"


def truncate_path(path: str, max_len: int = 50) -> str:
    """Shortens long file paths from the middle so the filename stays visible."""
    if len(path) <= max_len:
        return path
    parts = path.split("/")
    filename = parts[-1]
    if len(filename) >= max_len - 5:
        return "..." + filename[-(max_len - 5):]
    remaining = max_len - len(filename) - 4
    head = "/".join(parts[:-1])
    return f"{head[:remaining]}.../{filename}"


def score_bar(score: float, width: int = 20) -> str:
    """Text progress bar fallback for places we don't want a full chart, e.g. '████████░░ 82.0'"""
    filled = round((score / 100) * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled) + f" {format_score(score)}"


def split_high_medium_low(results: list) -> Tuple[list, list, list]:
    """Buckets a list of file-risk dicts (each with a 'score' key) by tier."""
    high, medium, low = [], [], []
    for item in results:
        tier = risk_tier(item.get("score", 0))
        if tier == "high":
            high.append(item)
        elif tier == "medium":
            medium.append(item)
        else:
            low.append(item)
    return high, medium, low
