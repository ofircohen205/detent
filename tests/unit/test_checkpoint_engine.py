"""Unit tests for CheckpointEngine and supporting types."""

from __future__ import annotations

from detent.checkpoint.savepoint import FileSnapshot


def test_file_snapshot_fields() -> None:
    snap = FileSnapshot(path="/src/main.py", content=b"hello\n", existed=True, permissions=0o644)
    assert snap.path == "/src/main.py"
    assert snap.content == b"hello\n"
    assert snap.existed is True
    assert snap.permissions == 0o644


def test_file_snapshot_nonexistent_file() -> None:
    snap = FileSnapshot(path="/src/new.py", content=None, existed=False, permissions=None)
    assert snap.existed is False
    assert snap.content is None
    assert snap.permissions is None
