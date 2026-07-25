"""
config.py
Central place for constants, scoring thresholds, and environment-driven settings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM settings ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-sonnet-5")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 1024))
# If no API key is set, scan_service falls back to templated (non-LLM) explanations
# so the demo still works offline.
LLM_ENABLED = bool(ANTHROPIC_API_KEY)

# --- Static analysis thresholds ---
MAX_FUNCTION_LENGTH = int(os.environ.get("MAX_FUNCTION_LENGTH", 50))   # lines
MAX_NESTING_DEPTH = int(os.environ.get("MAX_NESTING_DEPTH", 4))        # levels

# Comment markers we care about, with relative severity weights.
COMMENT_MARKERS = {
    "TODO": 1.0,
    "FIXME": 2.0,
    "HACK": 1.5,
    "XXX": 1.5,
    "BUG": 2.5,
}

# File extensions to scan, mapped to a rough "language" bucket.
SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
}

# Directories to always skip during a scan.
IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "env",
    "dist", "build", ".next", ".idea", ".vscode", "coverage",
    "site-packages", ".mypy_cache", ".pytest_cache",
}

# --- Git history settings ---
GIT_LOG_SINCE_MONTHS = int(os.environ.get("GIT_LOG_SINCE_MONTHS", 6))

# --- Scoring weights ---
# Impact score blends these signals (each normalized 0-1) using these weights.
IMPACT_WEIGHTS = {
    "todo_density": 0.35,
    "function_length": 0.30,
    "nesting_depth": 0.35,
}

# Final score combines impact and frequency-of-change.
# total_score = (IMPACT_ALPHA * impact) + (FREQUENCY_ALPHA * frequency) + (BOTH_BONUS * impact * frequency)
# The multiplicative bonus rewards files that are BOTH risky and actively churned.
IMPACT_ALPHA = 0.4
FREQUENCY_ALPHA = 0.3
BOTH_BONUS = 0.3

# How many top-ranked files get an LLM-generated narration.
TOP_N_FOR_NARRATION = 5

# Max file size (bytes) we'll bother reading during static analysis.
MAX_FILE_SIZE_BYTES = 500_000
