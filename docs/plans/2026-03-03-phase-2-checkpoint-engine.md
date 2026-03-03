# Phase 2 — Checkpoint Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the checkpoint engine — in-memory SAVEPOINTs with shadow git backup and atomic rollback — so verification logic can be non-destructive.

**Architecture:** `FileSnapshot` captures file state at savepoint time. `CheckpointEngine` maintains an in-memory registry (`dict[str, list[FileSnapshot]]`) guarded by `asyncio.Lock`, performs atomic restores via `os.replace()`. `ShadowGit` backs every savepoint to a separate git repo at `.detent/shadow-git/` for crash durability.

**Tech Stack:** Python stdlib (`asyncio`, `os`, `dataclasses`, `json`, `pathlib`), git (subprocess via `asyncio.create_subprocess_exec`), pytest-asyncio.

---

## Task 1: `FileSnapshot` dataclass

**Files:**
- Create: `detent/checkpoint/savepoint.py`
- Test: `tests/unit/test_checkpoint_engine.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_checkpoint_engine.py
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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: `ImportError` — `detent.checkpoint.savepoint` does not exist yet.

**Step 3: Implement `FileSnapshot`**

```python
# detent/checkpoint/savepoint.py
"""Savepoint types and shadow git backup for CheckpointEngine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FileSnapshot:
    """Point-in-time snapshot of a single file's content and metadata.

    content=None means the file did not exist at savepoint time.
    existed=False means rollback should delete the file if it now exists.
    """

    path: str
    content: bytes | None  # None = file did not exist at savepoint time
    existed: bool
    permissions: int | None
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add detent/checkpoint/savepoint.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: add FileSnapshot dataclass"
```

---

## Task 2: `CheckpointEngine` — savepoint + list_savepoints

**Files:**
- Create: `detent/checkpoint/engine.py`
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append failing tests**

```python
# append to tests/unit/test_checkpoint_engine.py
import pytest
from pathlib import Path
from detent.checkpoint.engine import CheckpointEngine


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: `ImportError` — `detent.checkpoint.engine` does not exist.

**Step 3: Implement `CheckpointEngine` skeleton**

```python
# detent/checkpoint/engine.py
"""CheckpointEngine: in-memory SAVEPOINT registry with atomic rollback."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from detent.checkpoint.savepoint import FileSnapshot

logger = logging.getLogger(__name__)


class CheckpointEngine:
    """Manages file-level SAVEPOINTs with atomic rollback.

    In-memory snapshots provide sub-millisecond savepoint creation.
    Pass shadow_git_path to enable durable backup across process restarts.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, list[FileSnapshot]] = {}
        self._lock = asyncio.Lock()

    async def savepoint(self, ref: str, files: list[str]) -> None:
        """Capture a snapshot of each file before a write operation.

        Args:
            ref: Unique name for this savepoint, e.g. "chk_before_write_004".
            files: Absolute paths to snapshot. Non-existent paths are recorded
                   with existed=False so rollback knows to delete them.
        """
        snapshots: list[FileSnapshot] = []
        for path_str in files:
            path = Path(path_str)
            if path.exists():
                content = path.read_bytes()
                permissions = path.stat().st_mode & 0o777
                snapshots.append(
                    FileSnapshot(
                        path=path_str,
                        content=content,
                        existed=True,
                        permissions=permissions,
                    )
                )
            else:
                snapshots.append(
                    FileSnapshot(path=path_str, content=None, existed=False, permissions=None)
                )

        async with self._lock:
            self._snapshots[ref] = snapshots

        logger.info("[checkpoint] savepoint '%s' captured %d file(s)", ref, len(snapshots))

    async def list_savepoints(self) -> list[str]:
        """Return the refs of all active savepoints."""
        async with self._lock:
            return list(self._snapshots.keys())
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: 6 PASSED.

**Step 5: Commit**

```bash
git add detent/checkpoint/engine.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: add CheckpointEngine savepoint and list_savepoints"
```

---

## Task 3: `CheckpointEngine.rollback` + `discard`

**Files:**
- Modify: `detent/checkpoint/engine.py`
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append failing tests**

```python
# append to tests/unit/test_checkpoint_engine.py

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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: 6 new failures — `rollback` and `discard` not implemented.

**Step 3: Add `rollback` and `discard` to `CheckpointEngine`**

Append these methods inside the `CheckpointEngine` class in `detent/checkpoint/engine.py`:

```python
    async def rollback(self, ref: str) -> None:
        """Restore all files to their state at savepoint time.

        - Files that existed at savepoint: content atomically restored via os.replace().
        - Files that did not exist at savepoint: deleted if present now.

        Args:
            ref: Savepoint ref to roll back to.

        Raises:
            KeyError: If ref has no recorded savepoint.
        """
        async with self._lock:
            snapshots = self._snapshots.get(ref)

        if snapshots is None:
            raise KeyError(f"No savepoint found for ref '{ref}'")

        for snap in snapshots:
            path = Path(snap.path)
            if snap.existed:
                # Atomically restore: write to sibling tmp, then os.replace
                tmp = path.with_suffix(path.suffix + ".detent-tmp")
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(snap.content)  # type: ignore[arg-type]
                os.replace(tmp, path)
                if snap.permissions is not None:
                    os.chmod(path, snap.permissions)
            else:
                # File was created after savepoint — delete it
                if path.exists():
                    path.unlink()

        logger.info(
            "[checkpoint] rolled back to '%s' (%d file(s) restored)", ref, len(snapshots)
        )

    async def discard(self, ref: str) -> None:
        """Remove a savepoint from the registry.

        No-op if ref does not exist.

        Args:
            ref: Savepoint ref to discard.
        """
        async with self._lock:
            self._snapshots.pop(ref, None)
        logger.info("[checkpoint] discarded savepoint '%s'", ref)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: 12 PASSED.

**Step 5: Commit**

```bash
git add detent/checkpoint/engine.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: add CheckpointEngine rollback and discard"
```

---

## Task 4: Edge case tests — multiple savepoints, concurrency, atomic writes

**Files:**
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append edge case tests**

```python
# append to tests/unit/test_checkpoint_engine.py
import asyncio


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
```

**Step 2: Run tests (no new code needed)**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: all PASSED. If any fail, fix `engine.py` before committing.

**Step 3: Commit**

```bash
git add tests/unit/test_checkpoint_engine.py
git commit -m "test: add edge case tests for CheckpointEngine"
```

---

## Task 5: `ShadowGit` — init + commit

Shadow git layout inside `repo_path`:
```
.git/
snapshots/
    <ref>/
        meta.json          # [{path, existed, permissions, has_content}]
        files/
            <relative-path>  # file content blob (only if existed=True)
```

**Files:**
- Modify: `detent/checkpoint/savepoint.py`
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append failing tests**

```python
# append to tests/unit/test_checkpoint_engine.py
from detent.checkpoint.savepoint import ShadowGit


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py::test_shadow_git_init_creates_repo tests/unit/test_checkpoint_engine.py::test_shadow_git_commit_stores_content -v
```
Expected: `ImportError` — `ShadowGit` not defined.

**Step 3: Append `ShadowGit` to `detent/checkpoint/savepoint.py`**

```python
# append to detent/checkpoint/savepoint.py
import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_GIT_USER_EMAIL = "detent@localhost"
_GIT_USER_NAME = "Detent"


class ShadowGit:
    """Durable backup of savepoints using a shadow git repository.

    Each savepoint is stored as a directory snapshots/<ref>/ containing
    a meta.json and file blobs. The directory is committed to git for
    durability across process crashes.

    The repo is initialized lazily on the first savepoint.
    """

    def __init__(self, repo_path: Path) -> None:
        self._repo = repo_path
        self._initialized = False

    async def _run_git(self, *args: str) -> str:
        """Run a git command inside the shadow repo."""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=self._repo,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed: {stderr.decode().strip()}"
            )
        return stdout.decode()

    async def init(self) -> None:
        """Initialize the shadow git repository. Safe to call multiple times."""
        self._repo.mkdir(parents=True, exist_ok=True)
        await self._run_git("init")
        await self._run_git("config", "user.email", _GIT_USER_EMAIL)
        await self._run_git("config", "user.name", _GIT_USER_NAME)
        self._initialized = True
        logger.debug("[shadow-git] initialized at %s", self._repo)

    async def commit(self, ref: str, files: list[FileSnapshot]) -> None:
        """Write a savepoint directory to the shadow repo and commit it.

        Args:
            ref: Savepoint reference name.
            files: Snapshots to persist.
        """
        if not self._initialized:
            await self.init()

        snapshot_dir = self._repo / "snapshots" / ref
        files_dir = snapshot_dir / "files"
        files_dir.mkdir(parents=True, exist_ok=True)

        meta = []
        for snap in files:
            meta.append(
                {
                    "path": snap.path,
                    "existed": snap.existed,
                    "permissions": snap.permissions,
                    "has_content": snap.content is not None,
                }
            )
            if snap.content is not None:
                dest = files_dir / snap.path.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(snap.content)

        (snapshot_dir / "meta.json").write_text(json.dumps(meta, indent=2))

        await self._run_git("add", "-A")
        await self._run_git("commit", "--allow-empty", "-m", f"savepoint: {ref}")
        logger.debug(
            "[shadow-git] committed savepoint '%s' (%d file(s))", ref, len(files)
        )
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py::test_shadow_git_init_creates_repo tests/unit/test_checkpoint_engine.py::test_shadow_git_commit_stores_content -v
```
Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add detent/checkpoint/savepoint.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: add ShadowGit init and commit"
```

---

## Task 6: `ShadowGit.restore` + `ShadowGit.reset`

**Files:**
- Modify: `detent/checkpoint/savepoint.py`
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append failing tests**

```python
# append to tests/unit/test_checkpoint_engine.py


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py::test_shadow_git_restore_roundtrip tests/unit/test_checkpoint_engine.py::test_shadow_git_reset_removes_snapshot -v
```
Expected: `AttributeError` — `restore` and `reset` not implemented.

**Step 3: Append `restore` and `reset` to `ShadowGit`**

```python
    async def restore(self, ref: str) -> list[FileSnapshot]:
        """Read saved snapshots back from the shadow repo.

        Used for crash recovery when in-memory state is lost.

        Args:
            ref: Savepoint reference to restore.

        Returns:
            List of FileSnapshot objects as they were at savepoint time.

        Raises:
            FileNotFoundError: If no snapshot exists for ref.
        """
        snapshot_dir = self._repo / "snapshots" / ref
        meta_file = snapshot_dir / "meta.json"

        if not meta_file.exists():
            raise FileNotFoundError(f"No shadow-git snapshot for ref '{ref}'")

        meta = json.loads(meta_file.read_text())
        files_dir = snapshot_dir / "files"
        snapshots = []

        for entry in meta:
            content: bytes | None = None
            if entry["has_content"]:
                blob = files_dir / entry["path"].lstrip("/")
                content = blob.read_bytes() if blob.exists() else None
            snapshots.append(
                FileSnapshot(
                    path=entry["path"],
                    content=content,
                    existed=entry["existed"],
                    permissions=entry["permissions"],
                )
            )

        return snapshots

    async def reset(self, ref: str) -> None:
        """Remove a savepoint's snapshot directory from the shadow repo.

        Args:
            ref: Savepoint reference to delete.
        """
        import shutil

        snapshot_dir = self._repo / "snapshots" / ref
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
            await self._run_git("add", "-A")
            await self._run_git("commit", "--allow-empty", "-m", f"discard: {ref}")
            logger.debug("[shadow-git] removed snapshot '%s'", ref)
```

**Step 4: Run the full test suite**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: all PASSED.

**Step 5: Commit**

```bash
git add detent/checkpoint/savepoint.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: add ShadowGit restore and reset"
```

---

## Task 7: Wire `ShadowGit` into `CheckpointEngine`

**Files:**
- Modify: `detent/checkpoint/engine.py`
- Modify: `tests/unit/test_checkpoint_engine.py`

**Step 1: Append failing tests**

```python
# append to tests/unit/test_checkpoint_engine.py


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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py::test_checkpoint_engine_shadow_git_backup tests/unit/test_checkpoint_engine.py::test_checkpoint_engine_discard_cleans_shadow -v
```
Expected: `TypeError` — `CheckpointEngine` does not accept `shadow_git_path`.

**Step 3: Update `CheckpointEngine` in `detent/checkpoint/engine.py`**

Update the import line:
```python
from detent.checkpoint.savepoint import FileSnapshot, ShadowGit
```

Replace `__init__`, `savepoint`, and `discard` with:

```python
    def __init__(self, shadow_git_path: Path | None = None) -> None:
        self._snapshots: dict[str, list[FileSnapshot]] = {}
        self._lock = asyncio.Lock()
        self._shadow: ShadowGit | None = (
            ShadowGit(repo_path=shadow_git_path) if shadow_git_path is not None else None
        )

    async def savepoint(self, ref: str, files: list[str]) -> None:
        """Capture a snapshot of each file before a write operation."""
        snapshots: list[FileSnapshot] = []
        for path_str in files:
            path = Path(path_str)
            if path.exists():
                content = path.read_bytes()
                permissions = path.stat().st_mode & 0o777
                snapshots.append(
                    FileSnapshot(
                        path=path_str,
                        content=content,
                        existed=True,
                        permissions=permissions,
                    )
                )
            else:
                snapshots.append(
                    FileSnapshot(path=path_str, content=None, existed=False, permissions=None)
                )

        async with self._lock:
            self._snapshots[ref] = snapshots

        if self._shadow is not None:
            await self._shadow.commit(ref, snapshots)

        logger.info("[checkpoint] savepoint '%s' captured %d file(s)", ref, len(snapshots))

    async def discard(self, ref: str) -> None:
        """Remove a savepoint. No-op if ref does not exist."""
        async with self._lock:
            self._snapshots.pop(ref, None)

        if self._shadow is not None:
            await self._shadow.reset(ref)

        logger.info("[checkpoint] discarded savepoint '%s'", ref)
```

**Step 4: Run the full test suite**

```bash
uv run pytest tests/unit/test_checkpoint_engine.py -v
```
Expected: all PASSED (no regressions).

**Step 5: Commit**

```bash
git add detent/checkpoint/engine.py tests/unit/test_checkpoint_engine.py
git commit -m "feat: integrate ShadowGit into CheckpointEngine"
```

---

## Task 8: Export public API + final checks

**Files:**
- Modify: `detent/checkpoint/__init__.py`
- Modify: `docs/plans/v0.1/overview.md`

**Step 1: Update `detent/checkpoint/__init__.py`**

```python
# detent/checkpoint/__init__.py
"""Checkpoint engine — SAVEPOINT semantics for file operations."""

from detent.checkpoint.engine import CheckpointEngine
from detent.checkpoint.savepoint import FileSnapshot, ShadowGit

__all__ = ["CheckpointEngine", "FileSnapshot", "ShadowGit"]
```

**Step 2: Run full suite + static checks**

```bash
uv run pytest tests/ -v
uv run ruff check detent/ tests/
uv run ruff format --check detent/ tests/
uv run mypy detent/
```
All must pass before committing. Fix any issues.

**Step 3: Mark Phase 2 done in `docs/plans/v0.1/overview.md`**

Change:
```markdown
| [2](./phase-2-checkpoint-engine.md)     | Checkpoint Engine     | ⏳      | In-memory SAVEPOINTs + shadow git        |
```
To:
```markdown
| [2](./phase-2-checkpoint-engine.md)     | Checkpoint Engine     | ✅ Done | In-memory SAVEPOINTs + shadow git        |
```

**Step 4: Final commit**

```bash
git add detent/checkpoint/__init__.py docs/plans/v0.1/overview.md
git commit -m "feat: export CheckpointEngine public API and mark phase 2 done"
```

---

## Verification

```bash
# All tests pass
uv run pytest tests/ -v

# Coverage on checkpoint package (target >80%)
uv run pytest tests/unit/test_checkpoint_engine.py --cov=detent.checkpoint --cov-report=term-missing

# Static checks
make check
```
