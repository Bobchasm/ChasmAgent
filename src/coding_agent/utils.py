from __future__ import annotations

from pathlib import Path

IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__", ".chasm", ".mypy_cache", ".ruff_cache"}


def ensure_within_root(root: Path, candidate: str | Path) -> Path:
    path = (root / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
    if root not in path.parents and path != root:
        raise ValueError(f"path escapes workspace: {candidate}")
    return path


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20] + "\n...<truncated>..."


def is_ignored_path(path: Path) -> bool:
    return any(part in IGNORED_PARTS for part in path.parts)
