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
