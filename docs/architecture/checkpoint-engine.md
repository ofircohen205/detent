# Checkpoint Engine and Atomic Rollback

## SAVEPOINT Semantics

The checkpoint engine applies database SAVEPOINT semantics to file operations. Each file-write tool call gets its own named savepoint (e.g., `chk_before_write_004`). Rollback is per-call — it restores only the files affected by that specific tool call, not the entire session.

This means multiple tool calls can be in-flight in parallel (within a single session) and each can be independently rolled back without affecting the others.

## In-Memory Snapshot Store

```
CheckpointEngine._snapshots: dict[str, list[FileSnapshot]]
```

Each savepoint maps a ref string to a list of `FileSnapshot` objects:

```python
class FileSnapshot:
    path: str           # absolute path
    content: bytes | None  # None if file did not exist
    existed: bool       # whether the file existed at savepoint time
    permissions: int    # st_mode & 0o777, restored on rollback
```

An `asyncio.Lock` (`_lock`) serializes all reads and writes to `_snapshots` to prevent data races under concurrent tool calls.

## Savepoint Creation

`savepoint(ref, files)` is called **before** the write operation begins:

```
for each path in files:
    if path.exists():
        read content bytes
        read permissions
        append FileSnapshot(path, content, existed=True, permissions)
    else:
        append FileSnapshot(path, content=None, existed=False, permissions=0)

async with self._lock:
    self._snapshots[ref] = snapshots
```

If shadow git is enabled, an async subprocess commit is made to `snapshots/<ref>/` in the shadow repo for durability across process restarts.

## Atomic Restore Mechanism

`rollback(ref)` restores all files from the snapshot atomically using `os.replace()`:

```
for each snapshot in self._snapshots[ref]:
    if snapshot.existed:
        write content to <path>.detent-tmp (sibling temp file)
        os.replace(<path>.detent-tmp, path)   ← atomic on POSIX
        chmod path to snapshot.permissions
    else:
        if path.exists():
            path.unlink()                      ← delete file created after savepoint
```

`os.replace()` performs an atomic rename on POSIX systems (Linux, macOS). The rename is atomic within the same filesystem. The `.detent-tmp` file is always on the same filesystem as the target because it uses a sibling path.

**Why not write directly?** Direct writes are not atomic — if the process crashes mid-write, the file is corrupted. The tmp → rename pattern ensures the file is either fully written or unchanged.

## New-File Deletion

When `snapshot.existed = False`, the file did not exist at savepoint time. If the write has already partially executed and created the file before the pipeline rejected it, rollback deletes the file:

```python
if not snapshot.existed and path.exists():
    path.unlink()
```

This handles the case where Detent's savepoint is taken before a multi-step write sequence and one step partially succeeds before the pipeline check.

## Shadow Git Backup

For durability across process restarts, pass `shadow_git_path` to `CheckpointEngine`:

```python
engine = CheckpointEngine(shadow_git_path=Path(".detent/shadow"))
```

`ShadowGit` lazily initializes a bare git repo at `shadow_git_path` on the first savepoint. Each savepoint is stored as:

```
.detent/shadow/
  snapshots/
    chk_before_write_004/
      meta.json           # { "ref": "...", "files": [...], "timestamp": "..." }
      0_src_main_py       # blob: original file content
      1_tests_test_main_py
      ...
```

`ShadowGit.commit()` and `ShadowGit.restore()` use `.resolve().is_relative_to()` to validate paths, preventing path traversal attacks where a malicious tool call references `../../etc/passwd`.

## Savepoint Lifecycle

```
intercept_tool_call(action):
    1. engine.savepoint(ref, [action.file_path])   ← BEFORE write
    2. pipeline.run(action)
    3a. if passed:  engine.discard(ref)            ← GC on success
    3b. if failed:  engine.rollback(ref)           ← restore on failure
```

`discard(ref)` removes the snapshot from `_snapshots` and deletes the shadow git directory if present. Without discard, the snapshot store would grow unbounded over long sessions.

## Performance Characteristics

| Operation | Typical latency | Notes |
|-----------|----------------|-------|
| `savepoint()` (in-memory only) | <1 ms | Simple read + dict insert under lock |
| `rollback()` (in-memory) | <5 ms | `os.replace()` per file, usually 1 file |
| `savepoint()` (with shadow git) | 20–100 ms | Async subprocess git commit |
| `rollback()` (with shadow git) | 30–200 ms | File restore + git cleanup |

The [benchmark suite](../../benchmarks/) measures savepoint and rollback latency under various file sizes. The CI threshold enforces rollback < 500 ms for 100 KB files.

## Observability

The engine emits OpenTelemetry spans:

- `detent.checkpoint.savepoint` — attributes: `detent.checkpoint_ref`, `detent.file_count`, `detent.total_bytes`
- `detent.checkpoint.rollback` — attributes: `detent.checkpoint_ref`, `detent.file_count`

Prometheus metric: `record_savepoint_size(ref, total_bytes)` tracks the cumulative snapshot size per session.

## See Also

- [Dual-Point Interception](./dual-point-interception.md)
- [Verification Pipeline](./verification-pipeline.md)
