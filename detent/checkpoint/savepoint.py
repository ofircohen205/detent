# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Savepoint types and shadow git backup for CheckpointEngine."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


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
            raise RuntimeError(f"git {' '.join(args)} failed: {stderr.decode().strip()}")
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
        logger.debug("[shadow-git] committed savepoint '%s' (%d file(s))", ref, len(files))

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
