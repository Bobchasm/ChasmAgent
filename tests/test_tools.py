from pathlib import Path

import pytest

from coding_agent.tools.filesystem import delete_path, read_file, replace_text, write_file
from coding_agent.utils import ensure_within_root


def test_ensure_within_root_blocks_escape(tmp_path: Path):
    with pytest.raises(ValueError):
        ensure_within_root(tmp_path, "../escape.txt")


def test_file_roundtrip(tmp_path: Path):
    assert "wrote" in write_file(tmp_path, "a/b.txt", "hello")
    assert read_file(tmp_path, "a/b.txt") == "hello"
    assert replace_text(tmp_path, "a/b.txt", "hello", "world") == "updated a/b.txt"
    assert read_file(tmp_path, "a/b.txt") == "world"


def test_delete_path_handles_files_and_non_empty_dirs(tmp_path: Path):
    write_file(tmp_path, "a/file.txt", "hello")
    write_file(tmp_path, "b/nested/file.txt", "world")
    assert delete_path(tmp_path, "a/file.txt") == "deleted a/file.txt"
    assert not (tmp_path / "a/file.txt").exists()
    assert delete_path(tmp_path, "b") == "deleted b"
    assert not (tmp_path / "b").exists()
