"""Unit tests for CheckpointEngine and supporting types."""

from __future__ import annotations

import pytest
from pathlib import Path

from detent.checkpoint.savepoint import FileSnapshot
from detent.checkpoint.engine import CheckpointEngine


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


@pytest.mark.asyncio
async def test_savepoint_captures_content(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_bytes(b'print("hello")\n')

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])

    assert "chk_001" in await engine.list_savepoints()


@pytest.mark.asyncio
async def test_savepoint_records_file_bytes(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_bytes(b'print("hello")\n')

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])

    snaps = engine._snapshots["chk_001"]
    assert len(snaps) == 1
    assert snaps[0].content == b'print("hello")\n'
    assert snaps[0].existed is True


@pytest.mark.asyncio
async def test_savepoint_nonexistent_file(tmp_path: Path) -> None:
    missing = tmp_path / "ghost.py"  # does not exist

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(missing)])

    snaps = engine._snapshots["chk_001"]
    assert snaps[0].existed is False
    assert snaps[0].content is None


@pytest.mark.asyncio
async def test_list_savepoints_empty() -> None:
    engine = CheckpointEngine()
    assert await engine.list_savepoints() == []


@pytest.mark.asyncio
async def test_rollback_restores_modified_file(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    original = b'print("original")\n'
    target.write_bytes(original)

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])

    target.write_bytes(b'print("modified")\n')
    await engine.rollback("chk_001")

    assert target.read_bytes() == original


@pytest.mark.asyncio
async def test_rollback_deletes_new_files(tmp_path: Path) -> None:
    new_file = tmp_path / "new.py"  # does not exist at savepoint time

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(new_file)])

    new_file.write_bytes(b'print("new")\n')  # created after savepoint
    await engine.rollback("chk_001")

    assert not new_file.exists()


@pytest.mark.asyncio
async def test_rollback_restores_deleted_files(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    original = b'print("original")\n'
    target.write_bytes(original)

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])

    target.unlink()  # deleted after savepoint
    await engine.rollback("chk_001")

    assert target.exists()
    assert target.read_bytes() == original


@pytest.mark.asyncio
async def test_rollback_unknown_ref_raises() -> None:
    engine = CheckpointEngine()
    with pytest.raises(KeyError, match="chk_missing"):
        await engine.rollback("chk_missing")


@pytest.mark.asyncio
async def test_discard_removes_savepoint(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_bytes(b"x\n")

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])
    assert "chk_001" in await engine.list_savepoints()

    await engine.discard("chk_001")
    assert "chk_001" not in await engine.list_savepoints()


@pytest.mark.asyncio
async def test_discard_unknown_ref_is_noop() -> None:
    engine = CheckpointEngine()
    await engine.discard("chk_ghost")  # must not raise
