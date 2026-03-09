"""Unit tests for CheckpointEngine and supporting types."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from detent.checkpoint.engine import CheckpointEngine
from detent.checkpoint.savepoint import FileSnapshot, ShadowGit


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


@pytest.mark.asyncio
async def test_multiple_savepoints_partial_rollback(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    v1, v2, v3 = b"# v1\n", b"# v2\n", b"# v3\n"

    target.write_bytes(v1)
    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])

    target.write_bytes(v2)
    await engine.savepoint("chk_002", [str(target)])

    target.write_bytes(v3)
    await engine.rollback("chk_002")

    assert target.read_bytes() == v2
    assert "chk_001" in await engine.list_savepoints()  # unaffected


@pytest.mark.asyncio
async def test_concurrent_savepoints(tmp_path: Path) -> None:
    engine = CheckpointEngine()
    paths = []
    for i in range(5):
        f = tmp_path / f"file_{i}.py"
        f.write_bytes(f"# file {i}\n".encode())
        paths.append(str(f))

    refs = [f"chk_{i:03d}" for i in range(5)]
    await asyncio.gather(*[engine.savepoint(refs[i], [paths[i]]) for i in range(5)])

    active = await engine.list_savepoints()
    assert set(refs) == set(active)


@pytest.mark.asyncio
async def test_no_tmp_files_left_after_rollback(tmp_path: Path) -> None:
    target = tmp_path / "main.py"
    target.write_bytes(b"# original\n")

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(target)])
    target.write_bytes(b"# modified\n")
    await engine.rollback("chk_001")

    assert list(tmp_path.glob("*.detent-tmp")) == []


@pytest.mark.asyncio
async def test_rollback_creates_parent_dirs(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "deep.py"
    deep.parent.mkdir(parents=True)
    deep.write_bytes(b"# deep\n")

    engine = CheckpointEngine()
    await engine.savepoint("chk_001", [str(deep)])

    deep.unlink()
    deep.parent.rmdir()

    await engine.rollback("chk_001")  # must recreate parent dirs

    assert deep.exists()
    assert deep.read_bytes() == b"# deep\n"


@pytest.mark.asyncio
async def test_shadow_git_init_creates_repo(tmp_path: Path) -> None:
    shadow = ShadowGit(repo_path=tmp_path / ".detent" / "shadow-git")
    await shadow.init()
    assert (tmp_path / ".detent" / "shadow-git" / ".git").is_dir()


@pytest.mark.asyncio
async def test_shadow_git_commit_stores_content(tmp_path: Path) -> None:
    shadow = ShadowGit(repo_path=tmp_path / ".detent" / "shadow-git")
    await shadow.init()

    snaps = [
        FileSnapshot(path="src/main.py", content=b'print("hello")\n', existed=True, permissions=0o644),
    ]
    await shadow.commit("chk_001", snaps)

    snapshot_dir = tmp_path / ".detent" / "shadow-git" / "snapshots" / "chk_001"
    assert snapshot_dir.is_dir()
    assert (snapshot_dir / "meta.json").exists()
    assert (snapshot_dir / "files" / "src" / "main.py").read_bytes() == b'print("hello")\n'


@pytest.mark.asyncio
async def test_shadow_git_restore_roundtrip(tmp_path: Path) -> None:
    shadow = ShadowGit(repo_path=tmp_path / ".detent" / "shadow-git")
    await shadow.init()

    original = [
        FileSnapshot(path="src/main.py", content=b'print("hello")\n', existed=True, permissions=0o644),
        FileSnapshot(path="src/missing.py", content=None, existed=False, permissions=None),
    ]
    await shadow.commit("chk_001", original)

    restored = await shadow.restore("chk_001")

    assert len(restored) == 2
    assert restored[0].path == "src/main.py"
    assert restored[0].content == b'print("hello")\n'
    assert restored[0].existed is True
    assert restored[1].path == "src/missing.py"
    assert restored[1].content is None
    assert restored[1].existed is False


@pytest.mark.asyncio
async def test_shadow_git_reset_removes_snapshot(tmp_path: Path) -> None:
    shadow = ShadowGit(repo_path=tmp_path / ".detent" / "shadow-git")
    await shadow.init()

    snaps = [FileSnapshot(path="src/a.py", content=b"a\n", existed=True, permissions=0o644)]
    await shadow.commit("chk_001", snaps)
    await shadow.reset("chk_001")

    snapshot_dir = tmp_path / ".detent" / "shadow-git" / "snapshots" / "chk_001"
    assert not snapshot_dir.exists()


@pytest.mark.asyncio
async def test_checkpoint_engine_shadow_git_backup(tmp_path: Path) -> None:
    shadow_path = tmp_path / ".detent" / "shadow-git"
    target = tmp_path / "main.py"
    target.write_bytes(b"# original\n")

    engine = CheckpointEngine(shadow_git_path=shadow_path)
    await engine.savepoint("chk_001", [str(target)])

    assert (shadow_path / ".git").is_dir()
    assert (shadow_path / "snapshots" / "chk_001" / "meta.json").exists()


@pytest.mark.asyncio
async def test_checkpoint_engine_discard_cleans_shadow(tmp_path: Path) -> None:
    shadow_path = tmp_path / ".detent" / "shadow-git"
    target = tmp_path / "main.py"
    target.write_bytes(b"# x\n")

    engine = CheckpointEngine(shadow_git_path=shadow_path)
    await engine.savepoint("chk_001", [str(target)])
    await engine.discard("chk_001")

    assert not (shadow_path / "snapshots" / "chk_001").exists()


@pytest.mark.asyncio
async def test_shadow_git_commit_rejects_path_traversal(tmp_path: Path) -> None:
    """ShadowGit.commit() must reject path traversal attempts."""
    shadow = ShadowGit(tmp_path / "shadow")
    await shadow.init()
    snap = FileSnapshot(
        path="/../../../tmp/evil.sh",
        content=b"evil",
        existed=False,
        permissions=0o644,
    )
    with pytest.raises(ValueError, match="Path traversal"):
        await shadow.commit("chk_000", [snap])


@pytest.mark.asyncio
async def test_shadow_git_restore_rejects_path_traversal(tmp_path: Path) -> None:
    """ShadowGit.restore() must reject path traversal in stored meta.json."""
    import json

    shadow = ShadowGit(tmp_path / "shadow")
    await shadow.init()

    snapshot_dir = shadow._repo / "snapshots" / "chk_evil"
    files_dir = snapshot_dir / "files"
    files_dir.mkdir(parents=True)
    meta = [{"path": "/../../../tmp/evil.sh", "existed": False, "permissions": None, "has_content": True}]
    (snapshot_dir / "meta.json").write_text(json.dumps(meta))

    with pytest.raises(ValueError, match="Path traversal"):
        await shadow.restore("chk_evil")
