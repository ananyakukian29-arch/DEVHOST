"""
core/static_analyzer.py
Walks a repo and computes, per file:
  - comment markers (TODO/FIXME/HACK/...) with line numbers
  - longest function/method length
  - deepest nesting level
Uses Python's `ast` module for .py files (accurate), and an indentation/brace
heuristic for everything else (good enough for ranking purposes).
"""
from __future__ import annotations

import ast
import os
import re
from typing import Dict, Iterable, List, Tuple

from backend.config import (
    COMMENT_MARKERS,
    IGNORED_DIRS,
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_EXTENSIONS,
)
from backend.models.schemas import CodeSmell, StaticSignals

# Matches "# TODO: fix this" / "// FIXME(name): ..." / "-- HACK ..." across common comment styles.
_MARKER_PATTERN = re.compile(
    r"(?:#|//|/\*|--|\*)\s*(" + "|".join(COMMENT_MARKERS.keys()) + r")\b[:\s]*(.*)",
    re.IGNORECASE,
)


def discover_files(repo_path: str) -> List[str]:
    """Return absolute paths of all source files worth scanning under repo_path."""
    results = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1]
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            full_path = os.path.join(root, fname)
            try:
                if os.path.getsize(full_path) > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue
            results.append(full_path)
    return results


def _find_comment_markers(lines: List[str]) -> Tuple[Dict[str, int], List[CodeSmell]]:
    """Scan raw lines (any language) for TODO/FIXME/HACK-style markers."""
    counts: Dict[str, int] = {marker: 0 for marker in COMMENT_MARKERS}
    smells: List[CodeSmell] = []
    for i, line in enumerate(lines, start=1):
        match = _MARKER_PATTERN.search(line)
        if match:
            marker = match.group(1).upper()
            detail = match.group(2).strip() or line.strip()
            counts[marker] = counts.get(marker, 0) + 1
            smells.append(CodeSmell(type=marker, line=i, detail=detail[:200]))
    return counts, smells


def _analyze_python(source: str) -> Tuple[int, int, List[CodeSmell]]:
    """Use the AST to get exact function lengths and nesting depth for Python files."""
    max_func_len = 0
    max_nesting = 0
    smells: List[CodeSmell] = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0, 0, smells

    def nesting_depth(node: ast.AST, depth: int = 0) -> int:
        deepest = depth
        nesting_nodes = (ast.If, ast.For, ast.While, ast.With, ast.Try)
        for child in ast.iter_child_nodes(node):
            child_depth = depth + 1 if isinstance(child, nesting_nodes) else depth
            deepest = max(deepest, nesting_depth(child, child_depth))
        return deepest

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", start)
            length = end - start + 1
            if length > max_func_len:
                max_func_len = length
            from backend.config import MAX_FUNCTION_LENGTH
            if length > MAX_FUNCTION_LENGTH:
                smells.append(CodeSmell(
                    type="LONG_FUNCTION",
                    line=start,
                    detail=f"`{node.name}` is {length} lines long (limit {MAX_FUNCTION_LENGTH})",
                ))

            depth = nesting_depth(node)
            if depth > max_nesting:
                max_nesting = depth
            from backend.config import MAX_NESTING_DEPTH
            if depth > MAX_NESTING_DEPTH:
                smells.append(CodeSmell(
                    type="DEEP_NESTING",
                    line=start,
                    detail=f"`{node.name}` nests {depth} levels deep (limit {MAX_NESTING_DEPTH})",
                ))

    return max_func_len, max_nesting, smells


# Heuristic function starts for non-Python C-style / brace languages.
_FUNC_START_PATTERNS = [
    re.compile(r"^\s*(export\s+)?(async\s+)?function\s+\w+\s*\("),          # JS/TS function foo(
    re.compile(r"^\s*(public|private|protected|static|\s)*\w[\w<>\[\]]*\s+\w+\s*\([^;]*\)\s*\{"),  # Java/C#/C++
    re.compile(r"^\s*\w+\s*[:=]\s*(async\s*)?\([^)]*\)\s*=>"),              # JS/TS arrow fn
    re.compile(r"^\s*def\s+\w+\s*\("),                                     # Ruby
    re.compile(r"^\s*func\s+\w+\s*\("),                                    # Go
]

_NESTING_OPEN = re.compile(r"[{]")
_NESTING_CLOSE = re.compile(r"[}]")


def _analyze_generic(lines: List[str]) -> Tuple[int, int, List[CodeSmell]]:
    """
    Brace/indentation heuristic for non-Python files.
    Not exact, but good enough to rank files relative to one another.
    """
    from backend.config import MAX_FUNCTION_LENGTH, MAX_NESTING_DEPTH

    max_func_len = 0
    max_nesting = 0
    smells: List[CodeSmell] = []

    depth = 0
    func_start_line = None
    func_start_depth = None

    for i, line in enumerate(lines, start=1):
        is_func_start = any(p.search(line) for p in _FUNC_START_PATTERNS)
        if is_func_start and func_start_line is None:
            func_start_line = i
            func_start_depth = depth

        opens = len(_NESTING_OPEN.findall(line))
        closes = len(_NESTING_CLOSE.findall(line))
        depth += opens
        depth = max(0, depth)

        relative_depth = depth - (func_start_depth or 0) if func_start_line else depth
        if relative_depth > max_nesting:
            max_nesting = relative_depth

        depth -= closes
        depth = max(0, depth)

        # Heuristic: function "ends" once brace depth returns to (or below) where it started.
        if func_start_line is not None and depth <= (func_start_depth or 0) and (opens or closes):
            length = i - func_start_line + 1
            if length > max_func_len:
                max_func_len = length
            if length > MAX_FUNCTION_LENGTH:
                smells.append(CodeSmell(
                    type="LONG_FUNCTION",
                    line=func_start_line,
                    detail=f"Function starting near line {func_start_line} is ~{length} lines long",
                ))
            func_start_line = None
            func_start_depth = None

    if max_nesting > MAX_NESTING_DEPTH:
        smells.append(CodeSmell(
            type="DEEP_NESTING",
            line=1,
            detail=f"File reaches ~{max_nesting} levels of brace nesting (limit {MAX_NESTING_DEPTH})",
        ))

    return max_func_len, max_nesting, smells


def analyze_file(file_path: str) -> StaticSignals:
    """Run static analysis on a single file and return its raw signals."""
    ext = os.path.splitext(file_path)[1]
    language = SUPPORTED_EXTENSIONS.get(ext, "unknown")

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except OSError:
        return StaticSignals()

    lines = source.splitlines()
    marker_counts, marker_smells = _find_comment_markers(lines)

    if language == "python":
        max_func_len, max_nesting, structure_smells = _analyze_python(source)
    else:
        max_func_len, max_nesting, structure_smells = _analyze_generic(lines)

    fixme = marker_counts.get("FIXME", 0) + marker_counts.get("BUG", 0)
    hack = marker_counts.get("HACK", 0) + marker_counts.get("XXX", 0)
    todo = marker_counts.get("TODO", 0)

    return StaticSignals(
        todo_count=todo,
        fixme_count=fixme,
        hack_count=hack,
        other_marker_count=0,
        max_function_length=max_func_len,
        max_nesting_depth=max_nesting,
        total_lines=len(lines),
        smells=marker_smells + structure_smells,
    )


def analyze_repo(repo_path: str) -> Dict[str, StaticSignals]:
    """Analyze every supported file under repo_path. Returns {relative_path: StaticSignals}."""
    results: Dict[str, StaticSignals] = {}
    for full_path in discover_files(repo_path):
        rel_path = os.path.relpath(full_path, repo_path)
        results[rel_path] = analyze_file(full_path)
    return results
