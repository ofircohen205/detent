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

"""SessionManager class for CLI session state."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class SessionManager:
    """Manages CLI session state (distinct from proxy.SessionManager)."""

    def __init__(self, session_dir: Path | str | None = None) -> None:
        """Initialize session manager.

        Args:
            session_dir: Directory to store session state (default: .detent/session)
        """
        self.session_dir = Path(session_dir or ".detent/session")

    def load_or_create(self) -> dict[str, Any]:
        """Load existing session or create new one.

        Returns:
            Session dictionary
        """
        session_file = self.session_dir / "default.json"

        if session_file.exists():
            try:
                return json.loads(session_file.read_text())  # type: ignore[no-any-return]
            except json.JSONDecodeError as e:
                logger.warning(f"Session file corrupted: {e}, creating new session")
                return self._create_new_session()

        return self._create_new_session()

    def _create_new_session(self) -> dict[str, Any]:
        """Create a new session."""
        session: dict[str, Any] = {
            "session_id": f"sess_{uuid4().hex[:12]}",
            "active": True,
            "started_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
            "checkpoints": [],
        }
        return session

    def save(self, session: dict[str, Any]) -> None:
        """Persist session to disk.

        Args:
            session: Session dictionary to save
        """
        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.session_dir / "default.json"
        session_file.write_text(json.dumps(session, indent=2))
        logger.debug(f"Session saved to {session_file}")

    def add_checkpoint(
        self,
        session: dict[str, Any],
        ref: str,
        file: str,
        status: str = "created",
    ) -> None:
        """Track checkpoint in session state.

        Args:
            session: Session dictionary
            ref: Checkpoint reference (e.g., "chk_before_write_000")
            file: File path associated with checkpoint
            status: Checkpoint status (created, rolled_back, restored, rollback_failed)
        """
        session["checkpoints"].append(
            {
                "ref": ref,
                "file": file,
                "created_at": datetime.now(UTC).isoformat(),
                "status": status,
            }
        )
        session["last_updated"] = datetime.now(UTC).isoformat()

    def get_checkpoint(self, session: dict[str, Any], ref: str) -> dict[str, Any] | None:
        """Retrieve checkpoint by reference.

        Args:
            session: Session dictionary
            ref: Checkpoint reference

        Returns:
            Checkpoint dictionary or None if not found
        """
        for chk in session["checkpoints"]:
            checkpoint = chk
            if checkpoint["ref"] == ref:
                return checkpoint  # type: ignore[no-any-return]
        return None

    def update_checkpoint_status(self, session: dict[str, Any], ref: str, status: str) -> None:
        """Update checkpoint status.

        Args:
            session: Session dictionary
            ref: Checkpoint reference
            status: New status
        """
        for chk in session["checkpoints"]:
            if chk["ref"] == ref:
                chk["status"] = status
                session["last_updated"] = datetime.now(UTC).isoformat()
                break
