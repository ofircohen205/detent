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
