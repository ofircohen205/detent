# Phase 2 — Checkpoint Engine

> **Status:** ✅ Design approved — ready for implementation
> **Depends on:** Phase 1  
> **Branch:** `feature/checkpoint-engine`

## Goal

Build the checkpoint engine — Detent's rollback safety net. Must be complete and tested before any verification logic, since rollback is what makes verification non-destructive.

## Files

### New

| File                                   | Description                                 |
| -------------------------------------- | ------------------------------------------- |
| `detent/checkpoint/engine.py`          | `CheckpointEngine` class                    |
| `detent/checkpoint/savepoint.py`       | `FileSnapshot` dataclass, `ShadowGit` class |
| `tests/unit/test_checkpoint_engine.py` | Unit tests                                  |

## Design

### CheckpointEngine

```python
class CheckpointEngine:
    async savepoint(ref: str, files: list[str]) -> None
    async rollback(ref: str) -> None
    async list_savepoints() -> list[str]
    async discard(ref: str) -> None
```

- **`savepoint(ref, files)`** — captures `FileSnapshot` (path, content bytes, existed flag, permissions) for each file
- **`rollback(ref)`** — restores files atomically: write to `.tmp`, `os.replace()`, delete files created after savepoint
- **`list_savepoints()`** — returns active savepoint refs
- **`discard(ref)`** — removes a savepoint from registry

### Internal State

- `_snapshots: dict[str, list[FileSnapshot]]` protected by `asyncio.Lock`
- Atomic restore: write to temp file, `os.replace()`, delete new files

### FileSnapshot

```python
@dataclass
class FileSnapshot:
    path: str
    content: bytes | None   # None = file didn't exist
    existed: bool
    permissions: int | None
```

### ShadowGit

Lives at `.detent/shadow-git/` inside the project root (gitignored). Initialized lazily on first `savepoint` call.

```python
class ShadowGit:
    async def init(self, repo_path: Path) -> None
    async def commit(self, ref: str, files: list[FileSnapshot]) -> None
    async def restore(self, ref: str) -> list[FileSnapshot]
    async def reset(self, ref: str) -> None
```

- All subprocess calls use `asyncio.create_subprocess_exec` (non-blocking)
- Files stored under their original paths in the shadow repo; committed with `ref` as message
- `restore` reads blobs back out and returns `FileSnapshot` objects — used when in-memory state is lost
- `reset` removes commits after `ref` (called by `discard`)
- In-memory snapshots provide speed; shadow git provides durability across process crashes

## Tests

All in `tests/unit/test_checkpoint_engine.py` using `tmp_path` fixtures (no external deps beyond git).

| Test | Description |
|---|---|
| `test_savepoint_captures_content` | Snapshot stores exact file bytes |
| `test_rollback_restores_content` | Modified file returns to savepoint state |
| `test_rollback_deletes_new_files` | Files created after savepoint are deleted on rollback |
| `test_rollback_restores_deleted_files` | Files deleted after savepoint are restored |
| `test_multiple_savepoints_partial_rollback` | Rolling back to intermediate ref leaves later state intact |
| `test_concurrent_savepoints` | `asyncio.Lock` prevents race conditions |
| `test_atomic_write` | No partial file state — `os.replace()` is atomic |
| `test_discard_removes_savepoint` | Discarded ref no longer appears in `list_savepoints` |
| `test_shadow_git_init` | Shadow repo is created on first savepoint |
| `test_shadow_git_commit_and_restore` | Blobs survive round-trip through shadow git |
