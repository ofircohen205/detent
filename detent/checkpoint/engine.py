"""CheckpointEngine: in-memory SAVEPOINT registry with atomic rollback."""

from __future__ import annotations

import asyncio
import logging
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
