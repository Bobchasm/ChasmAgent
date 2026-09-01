from __future__ import annotations

import fnmatch
from pathlib import Path

from ..utils import ensure_within_root, truncate_text
from ..utils import is_ignored_path


def read_file(root: Path, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
    file_path = ensure_within_root(root, path)
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if start_line is None and end_line is None:
        return text
    start = max((start_line or 1) - 1, 0)
    end = end_line if end_line is not None else len(lines)
    snippet = "\n".join(lines[start:end])
    return snippet


def write_file(root: Path, path: str, content: str) -> str:
    file_path = ensure_within_root(root, path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"wrote {file_path.relative_to(root)} ({len(content)} chars)"


def replace_text(root: Path, path: str, old: str, new: str, count: int = 1) -> str:
    file_path = ensure_within_root(root, path)
    text = file_path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError("target text not found")
    updated = text.replace(old, new, count)
    file_path.write_text(updated, encoding="utf-8")
    return f"updated {file_path.relative_to(root)}"


def list_files(root: Path, path: str = ".", pattern: str | None = None, max_depth: int = 3) -> str:
    base = ensure_within_root(root, path)
    rows: list[str] = []
    for candidate in sorted(base.rglob("*")):
        if candidate.is_dir():
            continue
        if is_ignored_path(candidate):
            continue
        rel = candidate.relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth + 1:
            continue
        if pattern and not fnmatch.fnmatch(candidate.name, pattern):
            continue
        rows.append(str(rel))
    return "\n".join(rows[:400]) if rows else "(empty)"


def search_text(root: Path, path: str, pattern: str, ignore_case: bool = False, max_results: int = 50) -> str:
    base = ensure_within_root(root, path)
    needle = pattern.lower() if ignore_case else pattern
    hits: list[str] = []
    for candidate in sorted(base.rglob("*")):
        if not candidate.is_file():
            continue
        if is_ignored_path(candidate):
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        haystack = text.lower() if ignore_case else text
        if needle not in haystack:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            cmp_line = line.lower() if ignore_case else line
            if needle in cmp_line:
                hits.append(f"{candidate.relative_to(root)}:{idx}: {truncate_text(line.strip(), 160)}")
                if len(hits) >= max_results:
                    return "\n".join(hits)
    return "\n".join(hits) if hits else "(no matches)"
